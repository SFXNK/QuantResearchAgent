"""Walk-forward analysis: stability of performance across sequential windows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from alphaforge.config import SimConfig
from alphaforge.strategy.base import Strategy
from alphaforge.types import MarketEvent

from .metrics import Metrics


@dataclass(slots=True)
class WalkForwardReport:
    window_sharpes: list[float]
    mean_sharpe: float
    std_sharpe: float
    frac_positive: float
    window_metrics: list[Metrics]

    @property
    def is_stable(self) -> bool:
        # Stable if a majority of windows are positive and dispersion is bounded.
        return self.frac_positive >= 0.5 and (
            self.std_sharpe <= abs(self.mean_sharpe) + 1.0
        )


def walk_forward(
    make_strategy: Callable[[], Strategy],
    events: Sequence[MarketEvent],
    sim_config: SimConfig,
    decision_interval_ns: int,
    n_windows: int,
) -> WalkForwardReport:
    from alphaforge.research.runner import run_backtest  # local import: avoid import cycle

    events = list(events)
    n = len(events)
    if n_windows < 1 or n == 0:
        return WalkForwardReport([], 0.0, 0.0, 0.0, [])

    bounds = np.linspace(0, n, n_windows + 1, dtype=int)
    sharpes: list[float] = []
    metrics_list: list[Metrics] = []
    for i in range(n_windows):
        chunk = events[bounds[i] : bounds[i + 1]]
        if len(chunk) < 2:
            continue
        _, metrics = run_backtest(make_strategy(), chunk, sim_config, decision_interval_ns)
        sharpes.append(metrics.sharpe)
        metrics_list.append(metrics)

    if not sharpes:
        return WalkForwardReport([], 0.0, 0.0, 0.0, [])
    arr = np.asarray(sharpes)
    return WalkForwardReport(
        window_sharpes=sharpes,
        mean_sharpe=float(arr.mean()),
        std_sharpe=float(arr.std(ddof=1)) if arr.shape[0] > 1 else 0.0,
        frac_positive=float((arr > 0).mean()),
        window_metrics=metrics_list,
    )
