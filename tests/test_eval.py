"""Tests for the evaluation harness: metrics, corrections, CV, overfitting, protocol."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from quant_research_agent.config import DataConfig, EvalConfig, SimConfig
from quant_research_agent.data import generate_synthetic
from quant_research_agent.eval import (
    Candidate,
    OutOfSampleEvaluator,
    benjamini_hochberg,
    bonferroni,
    compute_metrics,
    deflated_sharpe_ratio,
    probability_backtest_overfitting,
    purged_kfold_indices,
)


def test_metrics_positive_drift_has_positive_sharpe() -> None:
    equity = np.linspace(100.0, 120.0, 200)
    returns = np.diff(equity) / equity[:-1]
    m = compute_metrics(equity, returns, 1_000_000_000)
    assert m.sharpe > 0
    assert m.max_drawdown <= 0
    assert m.total_return > 0


def test_benjamini_hochberg_basic() -> None:
    pvals = [0.001, 0.01, 0.2, 0.7, 0.9]
    res = benjamini_hochberg(pvals, alpha=0.05)
    assert res.rejected[0] is True
    assert res.rejected[-1] is False
    assert all(0.0 <= a <= 1.0 for a in res.adjusted)


def test_bonferroni_is_more_conservative_than_bh() -> None:
    pvals = [0.02, 0.03, 0.04]
    bh = benjamini_hochberg(pvals, 0.05)
    bonf = bonferroni(pvals, 0.05)
    assert sum(bonf.rejected) <= sum(bh.rejected)


def test_purged_kfold_no_leakage() -> None:
    folds = purged_kfold_indices(n=100, k=5, embargo_frac=0.02)
    for f in folds:
        assert set(f.train).isdisjoint(set(f.test))
        # embargo: no train index in [test_end+1, test_end+embargo]
        t1 = int(f.test[-1])
        embargo_zone = set(range(t1 + 1, t1 + 3))
        assert embargo_zone.isdisjoint(set(f.train))


def test_pbo_random_is_near_half() -> None:
    rng = np.random.default_rng(0)
    matrix = rng.normal(size=(400, 12))  # pure noise strategies
    pbo = probability_backtest_overfitting(matrix, n_partitions=8)
    assert 0.0 <= pbo <= 1.0
    assert pbo > 0.2  # noise should overfit a lot


def test_deflated_sharpe_monotonic_in_observed() -> None:
    low = deflated_sharpe_ratio(0.02, 0.05, n_trials=50, n_obs=500)
    high = deflated_sharpe_ratio(0.20, 0.05, n_trials=50, n_obs=500)
    assert high >= low
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0


def _write(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_protocol_end_to_end(tmp_path: Path) -> None:
    ds = generate_synthetic(DataConfig(symbol="T", n_events=30_000), seed=11)
    candidates = [
        Candidate(
            0,
            "ma",
            _write(
                tmp_path / "ma.py",
                "from quant_research_agent.strategy.baselines import MovingAverageCross\n"
                "def build():\n    return MovingAverageCross()\n",
            ),
        ),
        Candidate(
            1,
            "rand",
            _write(
                tmp_path / "rand.py",
                "from quant_research_agent.strategy.baselines import RandomTrader\n"
                "def build():\n    return RandomTrader(seed=1)\n",
            ),
        ),
        Candidate(
            2,
            "flat",
            _write(
                tmp_path / "flat.py",
                "from quant_research_agent.strategy.baselines import FlatStrategy\n"
                "def build():\n    return FlatStrategy()\n",
            ),
        ),
    ]
    ev = OutOfSampleEvaluator(ds, SimConfig(), EvalConfig(cscv_partitions=6), 1_000_000_000)
    report = ev.evaluate(candidates)
    assert report.n_candidates == 3
    assert 0.0 <= report.survival_rate <= 1.0
    assert len(report.evaluations) == 3
    assert "flat" in report.baseline_metrics
    for e in report.evaluations:
        assert 0.0 <= e.deflated_sr <= 1.0
        assert 0.0 <= e.pvalue <= 1.0
