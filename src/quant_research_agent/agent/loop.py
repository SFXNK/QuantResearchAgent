"""The research agent loop.

A provider-agnostic tool-calling loop: the model proposes a hypothesis, writes
a strategy, backtests it, refines, and submits. The loop owns trajectory state,
token budgeting, and bounded iteration; tool *semantics* live in the registry,
and model *transport* lives in the gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from quant_research_agent.config import AgentConfig
from quant_research_agent.models.base import Message, Role
from quant_research_agent.models.gateway import ModelGateway
from quant_research_agent.tools.base import ToolContext
from quant_research_agent.tools.registry import ToolRegistry

from .context import trim_to_budget
from .prompts import SYSTEM_PROMPT, initial_task


@dataclass(slots=True)
class AgentResult:
    submitted: bool
    strategy_path: Path | None
    steps: int
    prompt_tokens: int
    completion_tokens: int
    hypotheses: list[str] = field(default_factory=list)
    final_val_metrics: dict | None = None
    trajectory: list[dict] = field(default_factory=list)
    forced_submit: bool = False  # harness submitted the last strategy on budget exhaustion

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ResearchAgent:
    def __init__(
        self,
        gateway: ModelGateway,
        registry: ToolRegistry,
        config: AgentConfig,
    ) -> None:
        self.gateway = gateway
        self.registry = registry
        self.config = config

    async def run(
        self,
        ctx: ToolContext,
        journal_summary: str = "(no prior experiments)",
        extra_context: str = "",
    ) -> AgentResult:
        task = initial_task(ctx.dataset.symbol, journal_summary)
        if extra_context:
            task = f"{task}\n\n{extra_context}"
        messages: list[Message] = [
            Message(role=Role.SYSTEM, content=SYSTEM_PROMPT),
            Message(role=Role.USER, content=task),
        ]
        schema = self.registry.openai_schema()
        prompt_tokens = 0
        completion_tokens = 0
        hypotheses: list[str] = []
        trajectory: list[dict] = []
        nudged = False
        steps = 0

        for steps in range(1, self.config.max_steps + 1):
            messages = trim_to_budget(messages, self.config.context_token_budget)
            resp = await self.gateway.chat(
                messages,
                tools=schema,
                temperature=self.config.temperature,
                max_tokens=2048,
            )
            prompt_tokens += resp.usage.prompt_tokens
            completion_tokens += resp.usage.completion_tokens
            messages.append(resp.message)

            if resp.message.content:
                first_line = resp.message.content.strip().splitlines()[0]
                if first_line.lower().startswith("hypothesis"):
                    hypotheses.append(first_line)
                trajectory.append({"type": "assistant", "content": resp.message.content})

            if not resp.message.tool_calls:
                if ctx.submitted or nudged:
                    break
                nudged = True
                messages.append(
                    Message(
                        role=Role.USER,
                        content="Continue using the tools, and submit when ready.",
                    )
                )
                continue

            for call in resp.message.tool_calls:
                result = await self.registry.dispatch(call, ctx)
                messages.append(
                    Message(
                        role=Role.TOOL,
                        content=result.content,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
                trajectory.append(
                    {"type": "tool", "name": call.name, "ok": result.ok, "content": result.content}
                )

            if ctx.submitted:
                break

            # Submit pressure: stop endless refinement before the budget runs out.
            if (
                ctx.last_backtest is not None
                and self.config.max_steps - steps <= 3
            ):
                messages.append(
                    Message(
                        role=Role.USER,
                        content=(
                            "You are almost out of steps. Stop refining and call "
                            "submit_strategy now with your single best strategy and a "
                            "one-line rationale."
                        ),
                    )
                )

        # Harness fallback: if the agent never submitted but produced a strategy that
        # was validated at least once, submit it so the run yields a candidate.
        forced_submit = False
        if not ctx.submitted and ctx.strategy_path is not None and ctx.last_backtest is not None:
            ctx.submitted = True
            ctx.submitted_strategy_path = ctx.strategy_path
            forced_submit = True
            trajectory.append({"type": "harness", "content": "forced submit on budget exhaustion"})

        final_val = ctx.last_backtest.get("metrics") if ctx.last_backtest else None
        hypotheses.extend(h for h in ctx.hypotheses if h not in hypotheses)
        return AgentResult(
            submitted=ctx.submitted,
            strategy_path=ctx.submitted_strategy_path,
            steps=steps,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            hypotheses=hypotheses,
            final_val_metrics=final_val,
            trajectory=trajectory,
            forced_submit=forced_submit,
        )
