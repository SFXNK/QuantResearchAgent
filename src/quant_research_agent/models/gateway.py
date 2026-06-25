"""Model gateway: caching, retries, rate-limiting, cost accounting, routing.

Wraps any `ModelClient`. Responsibilities the agent loop should not care about:
- cache lookups/stores by prompt hash (free, deterministic re-runs);
- bounded concurrency + minimum inter-request spacing (rate limits);
- exponential backoff with jitter on transient/429 errors;
- token + USD accounting via an injected usage callback.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from quant_research_agent.config import ModelConfig

from .base import ChatResponse, Message, ModelClient
from .cache import ResponseCache
from .echo import EchoModel
from .ollama import OllamaModel
from .openai_compat import AnthropicModel, OpenAICompatModel

# USD per 1K tokens (prompt, completion). Local/offline models are free.
_PRICES: dict[str, tuple[float, float]] = {
    "echo": (0.0, 0.0),
    "ollama": (0.0, 0.0),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "claude-3-5-sonnet-latest": (0.003, 0.015),
    # PackyAPI DeepSeek (USD/1K tokens, derived from /M pricing)
    "deepseek-v4-flash": (0.00025, 0.0005),
    "deepseek-v4-pro": (0.003, 0.006),
}

UsageCallback = Callable[[str, str, int, int, float, bool, float], None]


def build_model(cfg: ModelConfig) -> ModelClient:
    if cfg.provider == "echo":
        return EchoModel(cfg.model)
    if cfg.provider == "ollama":
        return OllamaModel(cfg.model, cfg.base_url or "http://localhost:11434/v1")
    if cfg.provider == "openai":
        return OpenAICompatModel(
            cfg.model,
            base_url=cfg.base_url or "https://api.openai.com/v1",
            api_key_env=cfg.api_key_env or "OPENAI_API_KEY",
        )
    if cfg.provider == "anthropic":
        return AnthropicModel(
            cfg.model,
            base_url=cfg.base_url or "https://api.anthropic.com/v1",
            api_key_env=cfg.api_key_env or "ANTHROPIC_API_KEY",
        )
    raise ValueError(f"unknown model provider {cfg.provider!r}")


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p_in, p_out = _PRICES.get(model, (0.0, 0.0))
    return prompt_tokens / 1000.0 * p_in + completion_tokens / 1000.0 * p_out


class ModelGateway:
    def __init__(
        self,
        cfg: ModelConfig,
        cache: ResponseCache | None = None,
        max_concurrency: int = 4,
        min_interval_s: float = 0.0,
        on_usage: UsageCallback | None = None,
    ) -> None:
        self.cfg = cfg
        self.client = build_model(cfg)
        self.cache = cache
        self._sem = asyncio.Semaphore(max_concurrency)
        self._min_interval = min_interval_s
        self._last_call = 0.0
        self._on_usage = on_usage

    @property
    def provider(self) -> str:
        return self.client.provider

    @property
    def model(self) -> str:
        return self.client.model

    async def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        temp = 0.7 if temperature is None else temperature
        mx = max_tokens if max_tokens is not None else self.cfg.max_tokens

        cache_key = None
        if self.cache is not None:
            cache_key = self.cache.key(
                self.provider, self.model, messages, tools, temp, mx
            )
            hit = self.cache.get(cache_key)
            if hit is not None:
                self._record(hit, cached=True, latency=0.0)
                return hit

        resp = await self._chat_with_retries(messages, tools, temp, mx)

        if self.cache is not None and cache_key is not None:
            self.cache.put(cache_key, resp)
        return resp

    async def _chat_with_retries(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> ChatResponse:
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._sem:
                    await self._respect_interval()
                    start = time.perf_counter()
                    resp = await self.client.chat(messages, tools, temperature, max_tokens)
                    latency = time.perf_counter() - start
                self._record(resp, cached=False, latency=latency)
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                retryable = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and (
                        exc.response.status_code in (408, 409, 429)
                        # any 5xx, incl. Cloudflare 520-524 from flaky proxies/origins
                        or exc.response.status_code >= 500
                    )
                )
                if not retryable or attempt > self.cfg.max_retries:
                    raise
                backoff = min(30.0, 0.5 * 2**attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(backoff)

    async def _respect_interval(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        wait = self._last_call + self._min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

    def _record(self, resp: ChatResponse, cached: bool, latency: float) -> None:
        if self._on_usage is None:
            return
        cost = 0.0 if cached else estimate_cost(
            resp.model, resp.usage.prompt_tokens, resp.usage.completion_tokens
        )
        self._on_usage(
            self.provider,
            resp.model,
            resp.usage.prompt_tokens,
            resp.usage.completion_tokens,
            cost,
            cached,
            latency,
        )
