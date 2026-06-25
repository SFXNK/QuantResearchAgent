"""Integrity suite for the data layer: partitioning, point-in-time, holdout isolation."""

from __future__ import annotations

import pytest

from quant_research_agent.config import DataConfig
from quant_research_agent.data import generate_synthetic
from quant_research_agent.data.dataset import LeakageError
from quant_research_agent.types import Partition


def _ds(n: int = 20_000, seed: int = 3):
    return generate_synthetic(DataConfig(symbol="T", n_events=n), seed)


def test_partitions_are_time_ordered_and_disjoint() -> None:
    ds = _ds()
    tr = ds.partition_time_range(Partition.TRAIN)
    va = ds.partition_time_range(Partition.VALIDATION)
    ho = ds.partition_time_range(Partition.HOLDOUT)
    # train ends before validation starts before holdout starts (embargo gap)
    assert tr[1] <= va[0]
    assert va[1] <= ho[0]
    # all partitions non-empty
    for p in Partition:
        assert len(ds.partition_events(p)) > 0


def test_embargo_gap_exists() -> None:
    cfg = DataConfig(symbol="T", n_events=20_000, embargo_frac=0.02)
    ds = generate_synthetic(cfg, 1)
    train_end = ds.bounds(Partition.TRAIN).end_idx
    val_start = ds.bounds(Partition.VALIDATION).start_idx
    assert val_start > train_end  # dropped embargo band


def test_as_of_never_returns_future() -> None:
    ds = _ds()
    evs = ds.partition_events(Partition.TRAIN)
    cutoff = evs[len(evs) // 2].ts
    seen = ds.as_of(Partition.TRAIN, cutoff)
    assert all(e.ts <= cutoff for e in seen)
    assert len(seen) <= len(evs)


def test_holdout_is_not_agent_accessible() -> None:
    ds = _ds()
    # Agent tools may read train/validation...
    assert len(ds.agent_events(Partition.TRAIN)) > 0
    assert len(ds.agent_events(Partition.VALIDATION)) > 0
    # ...but never the holdout.
    with pytest.raises(LeakageError):
        ds.agent_events(Partition.HOLDOUT)
