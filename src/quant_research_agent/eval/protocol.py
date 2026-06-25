"""The out-of-sample evaluation protocol.

This is the only place the HOLDOUT partition is ever touched, and it is run by
the harness -- never by the agent. It evaluates the whole population of
submitted candidates honestly: holdout performance vs baselines, walk-forward
stability, multiple-testing-corrected significance, the Deflated Sharpe Ratio
(accounting for the number of trials), and the population's Probability of
Backtest Overfitting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from quant_research_agent.config import EvalConfig, SimConfig
from quant_research_agent.data.dataset import Dataset
from quant_research_agent.strategy.baselines import baseline_strategies
from quant_research_agent.types import Partition

from .metrics import Metrics
from .multiple_testing import CorrectionResult, benjamini_hochberg, pvalue_from_sharpe
from .overfitting import (
    deflated_sharpe_ratio,
    probability_backtest_overfitting,
    sharpe_per_step,
)
from .walk_forward import WalkForwardReport, walk_forward

_SURVIVE_DSR = 0.95


@dataclass(slots=True)
class Candidate:
    experiment_id: int
    name: str
    strategy_path: Path
    val_metrics: dict | None = None
    hypothesis: str = ""


@dataclass(slots=True)
class CandidateEvaluation:
    candidate: Candidate
    holdout_metrics: Metrics
    walk_forward: WalkForwardReport
    sharpe_per_step: float
    pvalue: float
    adjusted_pvalue: float
    deflated_sr: float
    beats_baselines: bool
    significant: bool
    survived: bool


@dataclass(slots=True)
class EvaluationReport:
    evaluations: list[CandidateEvaluation]
    baseline_metrics: dict[str, Metrics]
    best_baseline_sharpe: float
    pbo: float
    n_candidates: int
    n_survivors: int
    correction: CorrectionResult
    fdr_alpha: float
    extra: dict = field(default_factory=dict)

    @property
    def survival_rate(self) -> float:
        return self.n_survivors / self.n_candidates if self.n_candidates else 0.0


def _skew_kurt(returns: np.ndarray) -> tuple[float, float]:
    if returns.shape[0] < 3:
        return 0.0, 3.0
    r = returns - returns.mean()
    sd = r.std()
    if sd < 1e-12:
        return 0.0, 3.0
    skew = float((r**3).mean() / sd**3)
    kurt = float((r**4).mean() / sd**4)
    return skew, kurt


class OutOfSampleEvaluator:
    def __init__(
        self,
        dataset: Dataset,
        sim_config: SimConfig,
        eval_config: EvalConfig,
        decision_interval_ns: int,
    ) -> None:
        self.dataset = dataset
        self.sim_config = sim_config
        self.eval_config = eval_config
        self.interval = decision_interval_ns

    def _holdout(self):  # noqa: ANN202
        # Harness-side access to the holdout. Agent tools cannot reach this.
        return self.dataset.partition_events(Partition.HOLDOUT)

    def _baselines(self) -> tuple[dict[str, Metrics], float]:
        from quant_research_agent.research.runner import run_backtest  # local import: avoid cycle

        holdout = self._holdout()
        metrics: dict[str, Metrics] = {}
        for strat in baseline_strategies(seed=0):
            _, m = run_backtest(strat, holdout, self.sim_config, self.interval)
            metrics[strat.name] = m
        best = max((m.sharpe for m in metrics.values()), default=0.0)
        return metrics, best

    def evaluate(self, candidates: Sequence[Candidate]) -> EvaluationReport:
        from quant_research_agent.research.runner import load_strategy, run_backtest  # avoid cycle

        holdout = self._holdout()
        baseline_metrics, best_baseline = self._baselines()

        returns_list: list[np.ndarray] = []
        holdout_metrics: list[Metrics] = []
        wf_reports: list[WalkForwardReport] = []
        sr_steps: list[float] = []
        pvalues: list[float] = []
        failed: list[bool] = []

        for c in candidates:
            # Agent-written strategies are untrusted: a crash in one candidate must
            # not abort the whole evaluation. A failed candidate is recorded as a
            # non-surviving entry with zero metrics and excluded from PBO.
            try:
                res, metrics = run_backtest(
                    load_strategy(c.strategy_path), holdout, self.sim_config, self.interval
                )
                wf = walk_forward(
                    lambda p=c.strategy_path: load_strategy(p),
                    holdout,
                    self.sim_config,
                    self.interval,
                    self.eval_config.walk_forward_windows,
                )
                srs = sharpe_per_step(res.returns)
                returns_list.append(res.returns)
                holdout_metrics.append(metrics)
                wf_reports.append(wf)
                sr_steps.append(srs)
                pvalues.append(pvalue_from_sharpe(srs, res.returns.shape[0]))
                failed.append(False)
            except Exception:  # noqa: BLE001 - buggy candidate code must not crash the harness
                returns_list.append(np.zeros(0))
                holdout_metrics.append(Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0))
                wf_reports.append(WalkForwardReport([], 0.0, 0.0, 0.0, []))
                sr_steps.append(0.0)
                pvalues.append(1.0)
                failed.append(True)

        correction = benjamini_hochberg(pvalues, self.eval_config.fdr_alpha)

        # PBO over the aligned return matrix of the *successful* candidate population.
        ok_returns = [r for r, f in zip(returns_list, failed) if not f and r.shape[0] > 0]
        pbo = float("nan")
        if len(ok_returns) >= 2:
            tmin = min(r.shape[0] for r in ok_returns)
            if tmin >= self.eval_config.cscv_partitions:
                matrix = np.column_stack([r[:tmin] for r in ok_returns])
                pbo = probability_backtest_overfitting(
                    matrix, self.eval_config.cscv_partitions
                )

        ok_sr = [s for s, f in zip(sr_steps, failed) if not f]
        sr_std = float(np.std(ok_sr, ddof=1)) if len(ok_sr) > 1 else 0.0
        evaluations: list[CandidateEvaluation] = []
        survivors = 0
        for i, c in enumerate(candidates):
            if failed[i]:
                evaluations.append(
                    CandidateEvaluation(
                        candidate=c,
                        holdout_metrics=holdout_metrics[i],
                        walk_forward=wf_reports[i],
                        sharpe_per_step=0.0,
                        pvalue=pvalues[i],
                        adjusted_pvalue=correction.adjusted[i],
                        deflated_sr=0.0,
                        beats_baselines=False,
                        significant=False,
                        survived=False,
                    )
                )
                continue
            skew, kurt = _skew_kurt(returns_list[i])
            dsr = deflated_sharpe_ratio(
                sr_steps[i],
                sr_std,
                n_trials=max(1, len(candidates)),
                n_obs=returns_list[i].shape[0],
                skew=skew,
                kurt=kurt,
            )
            beats = holdout_metrics[i].sharpe > best_baseline
            significant = correction.rejected[i]
            survived = bool(beats and significant and dsr >= _SURVIVE_DSR)
            survivors += int(survived)
            evaluations.append(
                CandidateEvaluation(
                    candidate=c,
                    holdout_metrics=holdout_metrics[i],
                    walk_forward=wf_reports[i],
                    sharpe_per_step=sr_steps[i],
                    pvalue=pvalues[i],
                    adjusted_pvalue=correction.adjusted[i],
                    deflated_sr=dsr,
                    beats_baselines=beats,
                    significant=significant,
                    survived=survived,
                )
            )

        return EvaluationReport(
            evaluations=evaluations,
            baseline_metrics=baseline_metrics,
            best_baseline_sharpe=best_baseline,
            pbo=pbo,
            n_candidates=len(candidates),
            n_survivors=survivors,
            correction=correction,
            fdr_alpha=self.eval_config.fdr_alpha,
        )
