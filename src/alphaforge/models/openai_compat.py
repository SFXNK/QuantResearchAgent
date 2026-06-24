"""OpenAI / Anthropic-compatible adapter.

`OpenAICompatModel` covers any endpoint speaking the OpenAI chat-completions
schema (OpenAI, Together, Groq, vLLM, Ollama, ...). `AnthropicModel` maps
Anthropic's Messages API onto the same `ChatResponse` shape.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from typing import Any

import httpx

from .base import ChatResponse, Message, Role, ToolCall, Usage


def _raise_for_status(resp: httpx.Response, base_url: str) -> None:
    """Like resp.raise_for_status() but surfaces the response body.

    Proxies (PackyAPI, OpenRouter, ...) put the real reason -- unknown model,
    tools unsupported, quota -- in the JSON body, which the default helper drops.
    Stays an HTTPStatusError so the gateway's retry logic still triggers on 429/5xx.
    """
    if resp.status_code < 400:
        return
    try:
        body = resp.text[:800]
    except Exception:
        body = "<unreadable body>"
    raise httpx.HTTPStatusError(
        f"{resp.status_code} from {base_url}/chat/completions: {body}",
        request=resp.request,
        response=resp,
    )


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_openai_choice(data: dict[str, Any], model: str) -> ChatResponse:
    choice = data["choices"][0]
    msg = choice["message"]
    tool_calls = [
        ToolCall(
            id=tc.get("id", f"call_{i}"),
            name=tc["function"]["name"],
            arguments=_arguments(tc["function"].get("arguments")),
        )
        for i, tc in enumerate(msg.get("tool_calls") or [])
    ]
    usage_raw = data.get("usage") or {}
    usage = Usage(
        prompt_tokens=usage_raw.get("prompt_tokens", 0),
        completion_tokens=usage_raw.get("completion_tokens", 0),
    )
    return ChatResponse(
        message=Message(
            role=Role.ASSISTANT, content=msg.get("content") or "", tool_calls=tool_calls
        ),
        usage=usage,
        model=model,
        finish_reason=choice.get("finish_reason", "stop"),
    )


class OpenAICompatModel:
    provider = "openai"

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        timeout_s: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ.get(api_key_env, "")
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
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            _raise_for_status(resp, self.base_url)
            return _parse_openai_choice(resp.json(), self.model)


class AnthropicModel:
    provider = "anthropic"

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-latest",
        base_url: str = "https://api.anthropic.com/v1",
        api_key_env: str = "ANTHROPIC_API_KEY",
        timeout_s: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ.get(api_key_env, "")
        self.timeout_s = timeout_s

    def _to_anthropic(self, messages: Sequence[Message]) -> tuple[str, list[dict[str, Any]]]:
        system = ""
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role is Role.SYSTEM:
                system += m.content + "\n"
            elif m.role is Role.TOOL:
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id or "",
                                "content": m.content,
                            }
                        ],
                    }
                )
            else:
                out.append({"role": m.role.value, "content": m.content})
        return system.strip(), out

    async def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        system, conv = self._to_anthropic(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": conv,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"].get("parameters", {}),
                }
                for t in tools
            ]
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(f"{self.base_url}/messages", json=payload, headers=headers)
            _raise_for_status(resp, self.base_url)
            data = resp.json()

        content = ""
        tool_calls: list[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(block["id"], block["name"], _arguments(block.get("input")))
                )
        usage_raw = data.get("usage") or {}
        usage = Usage(usage_raw.get("input_tokens", 0), usage_raw.get("output_tokens", 0))
        return ChatResponse(
            message=Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls),
            usage=usage,
            model=self.model,
            finish_reason=data.get("stop_reason", "stop"),
        )
