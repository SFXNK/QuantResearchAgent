"""Build TRAIN / VALIDATION / HOLDOUT bounds with an embargo gap.

Splitting is by event index (so partitions have balanced event counts) along
the time axis. Between each partition we drop an *embargo* band of events so a
strategy fit on TRAIN cannot trivially peek into VALIDATION/HOLDOUT through
slow-decaying features straddling the boundary.
"""

from __future__ import annotations

from collections.abc import Sequence

from quant_research_agent.config import DataConfig
from quant_research_agent.types import MarketEvent, Partition

from .dataset import Dataset, PartitionBounds


def partition_events(events: Sequence[MarketEvent], cfg: DataConfig, symbol: str) -> Dataset:
    n = len(events)
    embargo = int(n * cfg.embargo_frac)
    n_train = int(n * cfg.train_frac)
    n_val = int(n * cfg.val_frac)

    train = PartitionBounds(0, n_train)
    val_start = min(n, train.end_idx + embargo)
    val = PartitionBounds(val_start, min(n, val_start + n_val))
    hold_start = min(n, val.end_idx + embargo)
    hold = PartitionBounds(hold_start, n)

    bounds = {Partition.TRAIN: train, Partition.VALIDATION: val, Partition.HOLDOUT: hold}
    return Dataset(events, symbol, bounds)
