"""Cheap, dependency-free token estimation.

Good enough for budgeting and cost accounting without pulling a tokenizer. ~4
chars/token is the usual rule of thumb for English + code.
"""

from __future__ import annotations

from collections.abc import Sequence

from .base import Message


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens(messages: Sequence[Message]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(m.content)
        for tc in m.tool_calls:
            total += estimate_tokens(tc.name) + estimate_tokens(str(tc.arguments))
    return total
