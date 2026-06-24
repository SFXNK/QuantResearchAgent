"""Local Ollama adapter (the free default for real LLM runs).

Talks to the OpenAI-compatible endpoint Ollama exposes at /v1/chat/completions.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx

from .base import ChatResponse, Message, Role, ToolCall, Usage
from .openai_compat import _parse_openai_choice


class OllamaModel:
    provider = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        base_url: str = "http://localhost:11434/v1",
        timeout_s: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_wire() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = list(tools)

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return _parse_openai_choice(data, self.model)


def _normalize_tool_arguments(raw: Any) -> dict[str, Any]:  # pragma: no cover - helper
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


_ = (Message, Role, ToolCall, Usage)  # keep symbols referenced for adapters
