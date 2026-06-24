"""Evaluation harness: metrics, walk-forward, purged CV, overfitting, OOS protocol."""

from .metrics import Metrics, compute_metrics, periods_per_year
from .multiple_testing import (
    CorrectionResult,
    benjamini_hochberg,
    bonferroni,
    pvalue_from_sharpe,
)
from .overfitting import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probability_backtest_overfitting,
    sharpe_per_step,
)
from .protocol import (
    Candidate,
    CandidateEvaluation,
    EvaluationReport,
    OutOfSampleEvaluator,
)
from .purged_cv import Fold, purged_kfold_indices
from .walk_forward import WalkForwardReport, walk_forward

__all__ = [
    "Candidate",
    "CandidateEvaluation",
    "CorrectionResult",
    "EvaluationReport",
    "Fold",
    "Metrics",
    "OutOfSampleEvaluator",
    "WalkForwardReport",
    "benjamini_hochberg",
    "bonferroni",
    "compute_metrics",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "periods_per_year",
    "probability_backtest_overfitting",
    "purged_kfold_indices",
    "pvalue_from_sharpe",
    "sharpe_per_step",
    "walk_forward",
]
