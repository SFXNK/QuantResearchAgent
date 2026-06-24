"""Overfitting diagnostics: Deflated Sharpe Ratio and PBO (via CSCV).

References:
- Bailey & Lopez de Prado, "The Deflated Sharpe Ratio" (2014).
- Bailey, Borwein, Lopez de Prado & Zhu, "The Probability of Backtest
  Overfitting" (2015), Combinatorially-Symmetric Cross-Validation.
"""

from __future__ import annotations

import itertools
import math

import numpy as np

from .stats import norm_cdf, norm_ppf


def sharpe_per_step(returns: np.ndarray) -> float:
    if returns.shape[0] < 2:
        return 0.0
    sd = float(returns.std(ddof=1))
    if sd < 1e-12:
        return 0.0
    return float(returns.mean()) / sd


def expected_max_sharpe(n_trials: int, sr_std: float) -> float:
    """E[max SR] under N independent trials with SR dispersion `sr_std`."""
    if n_trials < 2 or sr_std <= 0:
        return 0.0
    gamma = 0.5772156649  # Euler-Mascheroni
    a = norm_ppf(1.0 - 1.0 / n_trials)
    b = norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    return sr_std * ((1.0 - gamma) * a + gamma * b)


def deflated_sharpe_ratio(
    observed_sr: float,
    sr_std_across_trials: float,
    n_trials: int,
    n_obs: int,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """Probability that the observed (per-step) Sharpe exceeds the expected max
    under the null, accounting for trial count, skew, and kurtosis."""
    sr0 = expected_max_sharpe(n_trials, sr_std_across_trials)
    if n_obs < 2:
        return 0.0
    denom = math.sqrt(max(1e-12, 1.0 - skew * observed_sr + (kurt - 1.0) / 4.0 * observed_sr**2))
    z = (observed_sr - sr0) * math.sqrt(n_obs - 1) / denom
    return norm_cdf(z)


def probability_backtest_overfitting(returns_matrix: np.ndarray, n_partitions: int = 8) -> float:
    """PBO via CSCV.

    `returns_matrix` is (T, M): per-step returns of M strategy configurations
    over T aligned steps. Returns the fraction of in-sample/out-of-sample splits
    in which the IS-best strategy lands in the bottom half OOS (i.e. its edge was
    an artifact of selection).
    """
    T, M = returns_matrix.shape
    if M < 2 or T < n_partitions:
        return float("nan")
    if n_partitions % 2 != 0:
        n_partitions -= 1

    # Split rows into S contiguous blocks of (roughly) equal size.
    blocks = np.array_split(np.arange(T), n_partitions)
    s_indices = list(range(n_partitions))

    logits: list[float] = []
    for is_combo in itertools.combinations(s_indices, n_partitions // 2):
        is_set = set(is_combo)
        is_rows = np.concatenate([blocks[i] for i in s_indices if i in is_set])
        oos_rows = np.concatenate([blocks[i] for i in s_indices if i not in is_set])

        is_sr = np.array([sharpe_per_step(returns_matrix[is_rows, m]) for m in range(M)])
        oos_sr = np.array([sharpe_per_step(returns_matrix[oos_rows, m]) for m in range(M)])

        best = int(np.argmax(is_sr))
        # relative rank of the IS-best strategy OOS, in (0, 1)
        rank = float((oos_sr < oos_sr[best]).sum() + 1) / (M + 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(rank / (1.0 - rank)))

    if not logits:
        return float("nan")
    # PBO = P(logit <= 0) = fraction of splits where best-IS underperforms OOS median
    arr = np.asarray(logits)
    return float((arr <= 0).mean())
