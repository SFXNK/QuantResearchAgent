"""Provider-agnostic chat types and the `ModelClient` protocol.

Modeled on OpenAI-style chat + tool calls so adapters are thin. Anthropic's
API is mapped onto the same shape inside its adapter.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


class Role(enum.StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on TOOL messages
    name: str | None = None

    def to_wire(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    # OpenAI spec requires arguments as a JSON string; strict
                    # backends (DeepSeek) reject a raw object/map.
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class ChatResponse:
    message: Message
    usage: Usage
    model: str
    cached: bool = False
    finish_reason: str = "stop"


class ModelClient(Protocol):
    """An async chat client. Implementations live in this package."""

    provider: str
    model: str

    async def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ChatResponse: ...
