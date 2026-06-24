"""Performance metrics computed from a backtest's return series.

All metrics operate on per-decision-step simple returns. Annualization uses the
number of decision steps per year implied by the decision interval, so Sharpe
etc. are comparable across configs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

_NS_PER_YEAR = 365 * 24 * 60 * 60 * 1_000_000_000


def periods_per_year(decision_interval_ns: int) -> float:
    return _NS_PER_YEAR / max(1, decision_interval_ns)


@dataclass(slots=True)
class Metrics:
    total_return: float
    ann_return: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    hit_rate: float
    n_steps: int

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}


def max_drawdown(equity: np.ndarray) -> float:
    if equity.shape[0] == 0:
        return 0.0
    running_max = np.maximum.accumulate(equity)
    # guard against zero/negative equity baselines
    denom = np.where(np.abs(running_max) > 1e-12, running_max, 1.0)
    drawdown = (equity - running_max) / denom
    return float(drawdown.min())


def sharpe_ratio(returns: np.ndarray, ppy: float) -> float:
    if returns.shape[0] < 2:
        return 0.0
    sd = float(returns.std(ddof=1))
    if sd < 1e-12:
        return 0.0
    return float(returns.mean() / sd * np.sqrt(ppy))


def sortino_ratio(returns: np.ndarray, ppy: float) -> float:
    if returns.shape[0] < 2:
        return 0.0
    downside = returns[returns < 0]
    dd = float(downside.std(ddof=1)) if downside.shape[0] > 1 else 0.0
    if dd < 1e-12:
        return 0.0
    return float(returns.mean() / dd * np.sqrt(ppy))


def compute_metrics(
    equity: np.ndarray, returns: np.ndarray, decision_interval_ns: int
) -> Metrics:
    ppy = periods_per_year(decision_interval_ns)
    n = int(returns.shape[0])
    if n == 0 or equity.shape[0] == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0)

    total_return = float(equity[-1] - equity[0])
    mean_r = float(returns.mean())
    ann_return = mean_r * ppy
    ann_vol = float(returns.std(ddof=1) * np.sqrt(ppy)) if n > 1 else 0.0
    sharpe = sharpe_ratio(returns, ppy)
    sortino = sortino_ratio(returns, ppy)
    mdd = max_drawdown(equity)
    calmar = ann_return / abs(mdd) if abs(mdd) > 1e-12 else 0.0
    hit_rate = float((returns > 0).mean())
    return Metrics(
        total_return=total_return,
        ann_return=ann_return,
        ann_vol=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=mdd,
        calmar=calmar,
        hit_rate=hit_rate,
        n_steps=n,
    )
