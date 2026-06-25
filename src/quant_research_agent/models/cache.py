"""Prompt-hash response cache.

Keyed on (provider, model, messages, tools, sampling params). A re-run with the
same inputs is free and deterministic, which is what makes whole-experiment
reproducibility practical. Stored as one JSON file per key under the cache dir.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .base import ChatResponse, Message, Role, ToolCall, Usage


def _hash_key(
    provider: str,
    model: str,
    messages: Sequence[Message],
    tools: Sequence[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "messages": [m.to_wire() for m in messages],
        "tools": list(tools or []),
        "temperature": round(temperature, 4),
        "max_tokens": max_tokens,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


class ResponseCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, *args: Any, **kwargs: Any) -> str:
        return _hash_key(*args, **kwargs)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> ChatResponse | None:
        path = self._path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        msg = Message(
            role=Role(data["role"]),
            content=data["content"],
            tool_calls=[
                ToolCall(tc["id"], tc["name"], tc["arguments"]) for tc in data.get("tool_calls", [])
            ],
        )
        usage = Usage(data["usage"]["prompt_tokens"], data["usage"]["completion_tokens"])
        return ChatResponse(
            message=msg, usage=usage, model=data["model"], cached=True, finish_reason=data["finish"]
        )

    def put(self, key: str, resp: ChatResponse) -> None:
        data = {
            "role": resp.message.role.value,
            "content": resp.message.content,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in resp.message.tool_calls
            ],
            "usage": {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            },
            "model": resp.model,
            "finish": resp.finish_reason,
        }
        self._path(key).write_text(json.dumps(data, indent=2))
