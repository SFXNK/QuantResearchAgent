"""Context-window / token budgeting.

When the running transcript exceeds the token budget we drop the oldest
*non-system* turns while keeping tool-call/tool-result pairs consistent, so the
model never sees a dangling tool result without its call.
"""

from __future__ import annotations

from quant_research_agent.models.base import Message, Role
from quant_research_agent.models.tokens import estimate_messages_tokens


def trim_to_budget(messages: list[Message], budget_tokens: int, keep_recent: int = 6) -> list[Message]:
    if estimate_messages_tokens(messages) <= budget_tokens:
        return messages

    system = [m for m in messages if m.role is Role.SYSTEM]
    rest = [m for m in messages if m.role is not Role.SYSTEM]

    # Always keep the most recent `keep_recent` turns; drop from the front otherwise.
    while len(rest) > keep_recent and estimate_messages_tokens(system + rest) > budget_tokens:
        rest.pop(0)

    trimmed = system + rest
    # Repair: a TOOL message whose matching assistant tool_call was dropped is removed.
    valid_ids: set[str] = set()
    for m in trimmed:
        for tc in m.tool_calls:
            valid_ids.add(tc.id)
    repaired = [
        m for m in trimmed if m.role is not Role.TOOL or (m.tool_call_id in valid_ids)
    ]
    return repaired
