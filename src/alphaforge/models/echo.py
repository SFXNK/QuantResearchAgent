"""Deterministic, offline `echo` model.

Not a real LLM: it scripts a minimal but complete research loop so the entire
harness runs end-to-end with zero cost and full determinism (CI, demos, parity
tests). Given the available tools it walks: propose hypothesis + write strategy
-> run backtest -> submit. Each experiment produces a *distinct* strategy
(parameters derived from the conversation hash) so the multiple-testing /
overfitting machinery has a real population to correct over.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from .base import ChatResponse, Message, Role, ToolCall, Usage
from .tokens import estimate_messages_tokens, estimate_tokens

_STRATEGY_TEMPLATE = '''\
"""Agent-generated strategy: {name}."""
from collections.abc import Sequence

from alphaforge.sim.base import Action, Observation
from alphaforge.types import Side


class GeneratedStrategy:
    name = "{name}"

    def __init__(self) -> None:
        self._mids: list[float] = []
        self.fast = {fast}
        self.slow = {slow}
        self.max_pos = {max_pos}

    def on_observation(self, obs: Observation) -> Sequence[Action]:
        mid = obs.mid
        if mid is None:
            return ()
        self._mids.append(mid)
        if len(self._mids) < self.slow:
            return ()
        window = self._mids[-self.slow:]
        fast_ma = sum(window[-self.fast:]) / self.fast
        slow_ma = sum(window) / self.slow
        want = {direction} if fast_ma > slow_ma else {anti}
        target = want * self.max_pos
        delta = target - obs.position
        if delta > 0:
            return (Action.market(Side.BUY, 1),)
        if delta < 0:
            return (Action.market(Side.SELL, 1),)
        return ()


def build() -> GeneratedStrategy:
    return GeneratedStrategy()
'''


def _last_tool_name(messages: Sequence[Message]) -> str | None:
    for m in reversed(messages):
        if m.role is Role.TOOL:
            return m.name
    return None


def _conversation_seed(messages: Sequence[Message]) -> int:
    blob = "".join(m.content for m in messages if m.role is Role.USER).encode()
    return int(hashlib.sha256(blob).hexdigest()[:8], 16)


class EchoModel:
    provider = "echo"

    def __init__(self, model: str = "echo") -> None:
        self.model = model

    async def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        tool_names = {t["function"]["name"] for t in (tools or [])}
        last = _last_tool_name(messages)
        seed = _conversation_seed(messages)

        content = ""
        tool_calls: list[ToolCall] = []

        if last is None and "write_strategy" in tool_names:
            fast = (4, 8, 12)[seed % 3]
            slow = (24, 48, 96)[(seed >> 2) % 3]
            direction = 1 if (seed >> 4) % 2 == 0 else -1
            name = f"gen_{seed % 100000}"
            code = _STRATEGY_TEMPLATE.format(
                name=name,
                fast=fast,
                slow=slow,
                max_pos=3,
                direction=direction,
                anti=-direction,
            )
            content = (
                f"Hypothesis: a {('momentum' if direction == 1 else 'mean-reversion')} signal on "
                f"a {fast}/{slow} moving-average crossover of the mid should capture short-horizon "
                f"autocorrelation. Implementing strategy {name}."
            )
            tool_calls = [
                ToolCall(
                    id="call_write",
                    name="write_strategy",
                    arguments={"filename": f"{name}.py", "code": code},
                )
            ]
        elif last == "write_strategy" and "run_backtest" in tool_names:
            content = "Strategy written. Backtesting on the validation partition."
            tool_calls = [
                ToolCall(
                    id="call_bt",
                    name="run_backtest",
                    arguments={"partition": "validation"},
                )
            ]
        elif last == "run_backtest" and "submit_strategy" in tool_names:
            content = "Backtest complete. Submitting the candidate for out-of-sample evaluation."
            tool_calls = [
                ToolCall(id="call_submit", name="submit_strategy", arguments={})
            ]
        else:
            content = "Done."
            if "submit_strategy" in tool_names:
                tool_calls = [ToolCall(id="call_submit", name="submit_strategy", arguments={})]

        prompt_tokens = estimate_messages_tokens(messages)
        completion_tokens = estimate_tokens(content) + sum(
            estimate_tokens(json.dumps(tc.arguments)) for tc in tool_calls
        )
        return ChatResponse(
            message=Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls),
            usage=Usage(prompt_tokens, completion_tokens),
            model=self.model,
            finish_reason="tool_calls" if tool_calls else "stop",
        )
