"""Adapter that exposes the compiled C++ sim core through the `SimCore` protocol.

The native module (`alphaforge_sim_native`) is optional. If it is not built,
`load_native()` returns None and callers fall back to `PythonSimCore`. Behavior
of the two is asserted equivalent in `tests/test_sim_parity.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from alphaforge.config import SimConfig
from alphaforge.types import BacktestResult, MarketEvent

from .base import Action, Observation, StrategyFn

try:  # pragma: no cover - depends on a native build being present
    import alphaforge_sim_native as _native  # type: ignore
except Exception:  # noqa: BLE001
    _native = None


def native_available() -> bool:
    return _native is not None


class NativeSimCore:
    """Thin wrapper translating to/from the nanobind module's flat API."""

    def __init__(self) -> None:
        if _native is None:  # pragma: no cover
            raise RuntimeError("native sim core not built; run cmake in sim_core/")

    def run(
        self,
        events: Sequence[MarketEvent],
        strategy: StrategyFn,
        config: SimConfig,
        decision_interval_ns: int,
    ) -> BacktestResult:  # pragma: no cover - exercised only with a native build
        sim = _native.MarketSimulator(
            config.tick_size,
            config.latency_ns,
            config.maker_fee_bps,
            config.taker_fee_bps,
            config.impact_coeff,
        )
        sim.load_events(
            np.fromiter((e.ts for e in events), dtype=np.int64, count=len(events)),
            np.fromiter((int(e.type) for e in events), dtype=np.int8, count=len(events)),
            np.fromiter((int(e.side) for e in events), dtype=np.int8, count=len(events)),
            np.fromiter((e.price for e in events), dtype=np.int64, count=len(events)),
            np.fromiter((e.qty for e in events), dtype=np.int64, count=len(events)),
            np.fromiter((e.order_id for e in events), dtype=np.int64, count=len(events)),
        )

        def callback(step: int, ts: int, bid: int, ask: int, pos: int, cash: float, eq: float):
            obs = Observation(
                step=step,
                ts=ts,
                best_bid=None if bid < 0 else bid,
                best_ask=None if ask < 0 else ask,
                position=pos,
                cash=cash,
                equity=eq,
            )
            out: list[tuple[int, int, int, int, int]] = []
            for a in strategy(obs):
                out.append((int(a.kind), int(a.side), a.price, a.qty, a.order_id))
            return out

        res = sim.run(decision_interval_ns, callback)
        equity = np.asarray(res.equity, dtype=np.float64)
        returns = (
            np.diff(equity) / np.where(np.abs(equity[:-1]) > 1e-12, equity[:-1], np.nan)
            if equity.shape[0] > 1
            else np.zeros(0)
        )
        returns = np.nan_to_num(returns)
        return BacktestResult(
            equity=equity,
            returns=returns,
            timestamps=np.asarray(res.timestamps, dtype=np.int64),
            n_trades=int(res.n_trades),
            turnover=float(res.turnover),
            final_position=int(res.final_position),
            fees_paid=float(res.fees_paid),
        )


_ = Action  # keep import for type symmetry with python_sim
