"""Backtest + submit tools.

`run_backtest` runs the current strategy on TRAIN/VALIDATION only, either
in-process or inside the hardened sandbox when one is attached to the context.
`submit_strategy` freezes the candidate for out-of-sample evaluation, which the
*harness* (not the agent) performs on the holdout set.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from alphaforge.research.runner import load_strategy, run_backtest, save_events
from alphaforge.types import Partition

from .base import Tool, ToolContext, ToolResult

_ALLOWED = {"train": Partition.TRAIN, "validation": Partition.VALIDATION}


class RunBacktestArgs(BaseModel):
    partition: str = Field(
        default="validation",
        description="Backtest on 'train' or 'validation'. Holdout is never available here.",
    )


class RunBacktestTool(Tool[RunBacktestArgs]):
    name = "run_backtest"
    description = (
        "Backtest the most recently written strategy on the chosen partition (train/validation). "
        "Returns Sharpe, returns, drawdown, trade count and fees. Execution is sandboxed when a "
        "sandbox is configured."
    )
    args_model = RunBacktestArgs

    async def run(self, args: RunBacktestArgs, ctx: ToolContext) -> ToolResult:
        if ctx.strategy_path is None:
            return ToolResult.error("no strategy written yet; call write_strategy first")
        p = _ALLOWED.get(args.partition.lower())
        if p is None:
            return ToolResult.error(
                f"partition must be one of {sorted(_ALLOWED)}; holdout is forbidden"
            )

        events = ctx.dataset.agent_events(p)
        if ctx.sandbox is not None:
            result = await self._run_sandboxed(ctx, events)
        else:
            _, metrics = run_backtest(
                load_strategy(ctx.strategy_path),
                events,
                ctx.sim_config,
                ctx.decision_interval_ns,
            )
            result = {"metrics": metrics.as_dict()}

        ctx.last_backtest = {"partition": args.partition, **result}
        m = result["metrics"]
        summary = (
            f"Backtest on {args.partition}: "
            f"sharpe={m['sharpe']:.3f}, ann_return={m['ann_return']:.4f}, "
            f"max_drawdown={m['max_drawdown']:.4f}, n_steps={int(m['n_steps'])}"
        )
        return ToolResult(ok=True, content=summary, data=result)

    async def _run_sandboxed(self, ctx: ToolContext, events) -> dict:  # noqa: ANN001
        events_path = ctx.workspace / "events.npz"
        sim_path = ctx.workspace / "sim_config.json"
        out_path = ctx.workspace / "bt_result.json"
        save_events(events, events_path)
        sim_path.write_text(ctx.sim_config.model_dump_json())
        ctx.sandbox.run_backtest(
            strategy_path=ctx.strategy_path,
            events_path=events_path,
            sim_config_path=sim_path,
            interval=ctx.decision_interval_ns,
            out_path=out_path,
        )
        return json.loads(out_path.read_text())


class SubmitStrategyArgs(BaseModel):
    rationale: str = Field(default="", description="Why this strategy should generalize.")


class SubmitStrategyTool(Tool[SubmitStrategyArgs]):
    name = "submit_strategy"
    description = (
        "Submit the current strategy as the final candidate. The harness then evaluates it once "
        "on the held-out set. Call this only after at least one backtest. Ends the session."
    )
    args_model = SubmitStrategyArgs

    async def run(self, args: SubmitStrategyArgs, ctx: ToolContext) -> ToolResult:
        if ctx.strategy_path is None:
            return ToolResult.error("nothing to submit; no strategy written")
        if ctx.last_backtest is None:
            return ToolResult.error("backtest the strategy before submitting")
        ctx.submitted = True
        ctx.submitted_strategy_path = ctx.strategy_path
        if args.rationale:
            ctx.hypotheses.append(args.rationale)
        return ToolResult(
            ok=True,
            content="Strategy submitted for out-of-sample evaluation.",
            data={"path": str(ctx.strategy_path)},
        )
