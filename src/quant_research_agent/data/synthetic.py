"""Synthetic order-flow generator.

A tractable agent-based / Hawkes hybrid: trades arrive with a self-exciting
intensity (clusters of activity, as in real markets), each trade exerts
temporary price impact on the mid, and a two-sided book is continuously posted
and cancelled around the mid. Fully deterministic given a seed, so backtests
are reproducible and the eval harness can be stress-tested on data with *known*
absence of exploitable structure (a critical null for the overfitting tests).
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from quant_research_agent.config import DataConfig
from quant_research_agent.types import EventType, MarketEvent, Partition, Side

from .dataset import Dataset
from .partition import partition_events


def generate_synthetic(cfg: DataConfig, seed: int) -> Dataset:
    rng = np.random.default_rng(seed)

    # Hawkes intensity: lambda = mu + sum_i alpha * exp(-beta (t - t_i))
    mu = 0.15
    alpha = 0.5
    beta = 0.6
    excitation = 0.0

    step_ns = 1_000_000  # 1ms
    dt = 1.0  # in "ms units" for the intensity
    levels = 3
    cancel_lag = 40

    mid = 1000.0
    ts = 0
    oid = 1
    events: list[MarketEvent] = []
    recent_ids: deque[int] = deque()

    while len(events) < cfg.n_events:
        ts += step_ns
        excitation *= math.exp(-beta * dt)
        intensity = mu + excitation

        m = int(round(mid))

        # Post fresh liquidity on both sides around the mid.
        for lvl in range(1, levels + 1):
            qty_b = int(rng.integers(20, 120))
            qty_a = int(rng.integers(20, 120))
            events.append(MarketEvent(ts, EventType.ADD, Side.BUY, m - lvl, qty_b, oid))
            recent_ids.append(oid)
            oid += 1
            events.append(MarketEvent(ts, EventType.ADD, Side.SELL, m + lvl, qty_a, oid))
            recent_ids.append(oid)
            oid += 1

        # Cancel stale liquidity to keep the book churning and bounded.
        while len(recent_ids) > cancel_lag * levels * 2:
            stale = recent_ids.popleft()
            events.append(MarketEvent(ts, EventType.CANCEL, Side.BUY, 0, 0, stale))

        # Trade arrival (thinned Poisson with self-excitation).
        p_trade = 1.0 - math.exp(-intensity * dt)
        if rng.random() < p_trade:
            # Aggressor side: slight momentum from current excitation sign, else noise.
            buy = rng.random() < 0.5
            aggressor = Side.BUY if buy else Side.SELL
            px = m + 1 if buy else m - 1
            qty = int(rng.integers(10, 60))
            events.append(MarketEvent(ts, EventType.TRADE, aggressor, px, qty, 0))
            excitation += alpha
            # Temporary price impact on the mid.
            mid += (0.15 if buy else -0.15)

        # Diffusive mid drift.
        mid += float(rng.normal(0.0, 0.05))
        mid = float(np.clip(mid, 50.0, 90_000.0))

    return partition_events(events, cfg, cfg.symbol)


def is_efficient_market(seed: int = 0, n: int = 20_000) -> Dataset:
    """A near-random null dataset: useful as a control where no strategy should win."""
    cfg = DataConfig(symbol="NULL", n_events=n)
    ds = generate_synthetic(cfg, seed)
    # sanity: holdout exists
    assert len(ds.partition_events(Partition.HOLDOUT)) > 0
    return ds
