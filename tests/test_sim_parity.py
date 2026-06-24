"""Native/Python sim parity + basic correctness.

The Python core is the executable spec; when the native module is built this
test asserts the two agree on the equity curve and trade count.
"""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.config import SimConfig
from alphaforge.sim import Action, Observation, PythonSimCore, native_available
from alphaforge.sim.native import NativeSimCore
from alphaforge.types import EventType, MarketEvent, Side


def _market(n: int = 2000) -> list[MarketEvent]:
    """A simple two-sided book with periodic trades that drift the mid up."""
    rng = np.random.default_rng(0)
    events: list[MarketEvent] = []
    ts = 0
    oid = 1
    mid = 1000
    for i in range(n):
        ts += 1_000_000  # 1ms
        mid += int(rng.integers(-1, 2))  # small random walk
        # post liquidity around the mid
        events.append(MarketEvent(ts, EventType.ADD, Side.BUY, mid - 1, 50, oid))
        oid += 1
        events.append(MarketEvent(ts, EventType.ADD, Side.SELL, mid + 1, 50, oid))
        oid += 1
        # occasional trades consuming a side
        if i % 5 == 0:
            aggressor = Side.BUY if rng.random() < 0.5 else Side.SELL
            px = mid + 1 if aggressor is Side.BUY else mid - 1
            events.append(MarketEvent(ts, EventType.TRADE, aggressor, px, 20, 0))
    return events


def _momentum_strategy(obs: Observation) -> list[Action]:
    """Cross the spread with a small market order when we see a one-sided book."""
    if obs.best_bid is None or obs.best_ask is None:
        return []
    if obs.step % 10 == 0 and obs.position < 5:
        return [Action.market(Side.BUY, 1)]
    if obs.step % 10 == 5 and obs.position > -5:
        return [Action.market(Side.SELL, 1)]
    return []


def test_python_core_runs() -> None:
    cfg = SimConfig()
    core = PythonSimCore()
    res = core.run(_market(), _momentum_strategy, cfg, decision_interval_ns=5_000_000)
    assert res.equity.shape[0] > 0
    assert res.n_trades > 0
    assert np.isfinite(res.equity).all()


def test_no_trades_zero_pnl() -> None:
    cfg = SimConfig()
    core = PythonSimCore()
    res = core.run(_market(), lambda obs: [], cfg, decision_interval_ns=5_000_000)
    assert res.n_trades == 0
    assert res.final_position == 0
    assert abs(res.fees_paid) < 1e-9


@pytest.mark.skipif(not native_available(), reason="native sim core not built")
def test_native_matches_python() -> None:
    cfg = SimConfig()
    events = _market()
    py = PythonSimCore().run(events, _momentum_strategy, cfg, 5_000_000)
    nat = NativeSimCore().run(events, _momentum_strategy, cfg, 5_000_000)
    assert py.n_trades == nat.n_trades
    np.testing.assert_allclose(py.equity, nat.equity, rtol=1e-9, atol=1e-6)
