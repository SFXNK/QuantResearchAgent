"""Inspect metrics of the most recent backtest."""

from __future__ import annotations

from pydantic import BaseModel

from .base import Tool, ToolContext, ToolResult


class ComputeMetricsArgs(BaseModel):
    pass


class ComputeMetricsTool(Tool[ComputeMetricsArgs]):
    name = "compute_metrics"
    description = "Return the full metric set from the most recent backtest."
    args_model = ComputeMetricsArgs

    async def run(self, args: ComputeMetricsArgs, ctx: ToolContext) -> ToolResult:
        if ctx.last_backtest is None:
            return ToolResult.error("no backtest has been run yet")
        metrics = ctx.last_backtest.get("metrics", {})
        lines = [f"{k}: {v:.6g}" for k, v in metrics.items()]
        return ToolResult(
            ok=True,
            content="Most recent backtest metrics:\n" + "\n".join(lines),
            data=metrics,
        )
