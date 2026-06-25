"""Purged + embargoed k-fold cross-validation indices.

For time-series, naive k-fold leaks information because samples adjacent to a
test fold are correlated with it. Purged k-fold drops training samples that
overlap the test fold, and an additional *embargo* band after each test fold
(Lopez de Prado, "Advances in Financial Machine Learning", ch. 7).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class Fold:
    train: np.ndarray
    test: np.ndarray


def purged_kfold_indices(n: int, k: int, embargo_frac: float = 0.01) -> list[Fold]:
    if k < 2 or n < k:
        raise ValueError("need k >= 2 and n >= k")
    embargo = int(n * embargo_frac)
    indices = np.arange(n)
    test_blocks = np.array_split(indices, k)

    folds: list[Fold] = []
    for block in test_blocks:
        test = block
        t0, t1 = int(test[0]), int(test[-1])
        # purge: drop any train index inside [t0, t1]; embargo: also drop up to t1+embargo
        lo = t0
        hi = min(n, t1 + embargo + 1)
        mask = np.ones(n, dtype=bool)
        mask[lo:hi] = False
        train = indices[mask]
        folds.append(Fold(train=train, test=test))
    return folds
