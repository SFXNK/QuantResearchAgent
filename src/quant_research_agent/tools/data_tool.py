"""Data-access tool. Restricted to TRAIN / VALIDATION; HOLDOUT is unreachable."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from quant_research_agent.data.dataset import LeakageError
from quant_research_agent.types import EventType, Partition

from .base import Tool, ToolContext, ToolResult

_ALLOWED = {"train": Partition.TRAIN, "validation": Partition.VALIDATION}


class DataSummaryArgs(BaseModel):
    partition: str = Field(
        default="train",
        description="Which partition to summarize: 'train' or 'validation'. Holdout is forbidden.",
    )


class DataSummaryTool(Tool[DataSummaryArgs]):
    name = "get_data_summary"
    description = (
        "Summarize the market data available for research (train or validation partition only). "
        "Returns event/trade counts, time span, and trade-price statistics. The holdout set is "
        "never accessible."
    )
    args_model = DataSummaryArgs

    async def run(self, args: DataSummaryArgs, ctx: ToolContext) -> ToolResult:
        p = _ALLOWED.get(args.partition.lower())
        if p is None:
            return ToolResult.error(
                f"partition must be one of {sorted(_ALLOWED)}; holdout is forbidden"
            )
        try:
            events = ctx.dataset.agent_events(p)
        except LeakageError as exc:
            return ToolResult.error(str(exc))

        trades = [e for e in events if e.type is EventType.TRADE]
        prices = np.asarray([e.price for e in trades], dtype=np.float64)
        vols = np.asarray([e.qty for e in trades], dtype=np.float64)
        if prices.shape[0]:
            stats = {
                "n_events": len(events),
                "n_trades": len(trades),
                "first_ts": events[0].ts,
                "last_ts": events[-1].ts,
                "price_min": float(prices.min()),
                "price_max": float(prices.max()),
                "price_mean": float(prices.mean()),
                "price_std": float(prices.std()),
                "vwap": float((prices * vols).sum() / max(vols.sum(), 1.0)),
                "total_volume": float(vols.sum()),
            }
        else:
            stats = {"n_events": len(events), "n_trades": 0}

        summary = "\n".join(f"{k}: {v}" for k, v in stats.items())
        return ToolResult(
            ok=True,
            content=f"Data summary ({args.partition}):\n{summary}",
            data=stats,
        )
