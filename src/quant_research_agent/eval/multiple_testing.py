"""Multiple-hypothesis correction.

When an agent generates many strategies, the best-looking holdout result is a
selection artifact unless we correct for the number of trials. We expose
Benjamini-Hochberg FDR control and Bonferroni FWER control, plus a p-value for
a Sharpe ratio under the no-skill null.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .stats import norm_cdf


def pvalue_from_sharpe(sharpe_per_step: float, n_obs: int) -> float:
    """One-sided p-value for SR > 0 under iid-normal returns.

    The t-statistic for a per-step Sharpe is approximately SR * sqrt(n_obs).
    """
    if n_obs < 2:
        return 1.0
    z = sharpe_per_step * np.sqrt(n_obs)
    return float(1.0 - norm_cdf(z))


@dataclass(slots=True)
class CorrectionResult:
    rejected: list[bool]
    adjusted: list[float]
    threshold: float
    method: str


def benjamini_hochberg(pvalues: list[float], alpha: float = 0.05) -> CorrectionResult:
    m = len(pvalues)
    if m == 0:
        return CorrectionResult([], [], 0.0, "benjamini_hochberg")
    order = np.argsort(pvalues)
    ranked = np.asarray(pvalues)[order]
    crit = (np.arange(1, m + 1) / m) * alpha
    below = ranked <= crit
    k = int(np.max(np.where(below)[0]) + 1) if below.any() else 0
    threshold = crit[k - 1] if k > 0 else 0.0

    rejected = [False] * m
    if k > 0:
        for i in range(k):
            rejected[int(order[i])] = True

    # BH-adjusted p-values (monotone)
    adj = np.empty(m)
    prev = 1.0
    for i in range(m - 1, -1, -1):
        val = min(prev, ranked[i] * m / (i + 1))
        adj[i] = val
        prev = val
    adjusted = [0.0] * m
    for idx, o in enumerate(order):
        adjusted[int(o)] = float(adj[idx])
    return CorrectionResult(rejected, adjusted, float(threshold), "benjamini_hochberg")


def bonferroni(pvalues: list[float], alpha: float = 0.05) -> CorrectionResult:
    m = len(pvalues)
    if m == 0:
        return CorrectionResult([], [], 0.0, "bonferroni")
    thr = alpha / m
    rejected = [p <= thr for p in pvalues]
    adjusted = [min(1.0, p * m) for p in pvalues]
    return CorrectionResult(rejected, adjusted, thr, "bonferroni")
