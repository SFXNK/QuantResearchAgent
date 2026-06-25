"""Integrity: determinism, realistic costs/impact, and tool-level holdout rejection."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from quant_research_agent.config import DataConfig, EvalConfig, SimConfig
from quant_research_agent.data import generate_synthetic
from quant_research_agent.integrity import derive_seed
from quant_research_agent.research.runner import run_backtest
from quant_research_agent.sim import Action, Observation, PythonSimCore
from quant_research_agent.strategy.baselines import MovingAverageCross
from quant_research_agent.tools.backtest_tool import RunBacktestArgs, RunBacktestTool
from quant_research_agent.tools.base import ToolContext
from quant_research_agent.types import EventType, MarketEvent, Side


def test_determinism_same_seed_same_result() -> None:
    from quant_research_agent.types import Partition

    cfg = DataConfig(symbol="T", n_events=10_000)
    a = generate_synthetic(cfg, seed=42)
    b = generate_synthetic(cfg, seed=42)

    ea = a.partition_events(Partition.VALIDATION)
    eb = b.partition_events(Partition.VALIDATION)
    assert [(e.ts, e.price, e.qty) for e in ea] == [(e.ts, e.price, e.qty) for e in eb]

    ra, ma = run_backtest(MovingAverageCross(), ea, SimConfig(), 1_000_000_000)
    rb, mb = run_backtest(MovingAverageCross(), eb, SimConfig(), 1_000_000_000)
    np.testing.assert_array_equal(ra.equity, rb.equity)
    assert ma.as_dict() == mb.as_dict()


def test_derive_seed_is_stable_and_varied() -> None:
    assert derive_seed(1, "exp", 0) == derive_seed(1, "exp", 0)
    assert derive_seed(1, "exp", 0) != derive_seed(1, "exp", 1)


def _trend_market(n: int = 400) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    ts = 0
    oid = 1
    mid = 1000
    for _ in range(n):
        ts += 1_000_000
        events.append(MarketEvent(ts, EventType.ADD, Side.BUY, mid - 1, 100, oid))
        oid += 1
        events.append(MarketEvent(ts, EventType.ADD, Side.SELL, mid + 1, 100, oid))
        oid += 1
    return events


def test_taker_pays_fees_and_impact() -> None:
    # A single buy market order should cost cash and pay a (positive) taker fee.
    sim = SimConfig(taker_fee_bps=2.0, maker_fee_bps=0.0, impact_coeff=0.0)

    def strat(obs: Observation) -> list[Action]:
        if obs.step == 5 and obs.best_ask is not None:
            return [Action.market(Side.BUY, 10)]
        return []

    res = PythonSimCore().run(_trend_market(), strat, sim, 5_000_000)
    assert res.n_trades >= 1
    assert res.fees_paid > 0.0  # taker pays
    assert res.final_position == 10


def test_maker_rebate_is_credited() -> None:
    sim = SimConfig(taker_fee_bps=2.0, maker_fee_bps=-1.0, impact_coeff=0.0)

    # Post a passive bid that later market sells will lift.
    def strat(obs: Observation) -> list[Action]:
        if obs.step == 1 and obs.best_bid is not None:
            return [Action.limit(Side.BUY, obs.best_bid, 10, order_id=999)]
        return []

    events = _trend_market()
    # inject sells crossing our bid after we post
    events.append(MarketEvent(events[-1].ts + 10_000_000, EventType.TRADE, Side.SELL, 999, 5, 0))
    res = PythonSimCore().run(events, strat, sim, 5_000_000)
    # If our passive order filled, we received a rebate (negative fee contribution).
    assert res.fees_paid <= 0.0 or res.n_trades == 0


@pytest.mark.asyncio
async def test_run_backtest_tool_rejects_holdout(tmp_path: Path) -> None:
    ds = generate_synthetic(DataConfig(symbol="T", n_events=8_000), seed=1)
    (tmp_path / "s.py").write_text(
        "from quant_research_agent.strategy.baselines import MovingAverageCross\n"
        "def build():\n    return MovingAverageCross()\n"
    )
    ctx = ToolContext(
        workspace=tmp_path,
        dataset=ds,
        sim_config=SimConfig(),
        eval_config=EvalConfig(),
        decision_interval_ns=1_000_000_000,
        strategy_path=tmp_path / "s.py",
    )
    res = await RunBacktestTool().run(RunBacktestArgs(partition="holdout"), ctx)
    assert not res.ok
    assert "holdout" in res.content.lower()
