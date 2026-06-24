"""Backtest-integrity guards.

Small, explicit helpers that make the harness's integrity rules executable
rather than aspirational. Used by the tools, eval protocol, and orchestrator.
"""

from __future__ import annotations

import hashlib

from alphaforge.data.dataset import Dataset, LeakageError
from alphaforge.types import MarketEvent, Partition


def ensure_agent_partition(p: Partition) -> None:
    """Raise if an agent-facing code path requests the holdout."""
    if not p.agent_accessible:
        raise LeakageError(f"partition {p.value!r} is off-limits to the agent")


def assert_no_future_events(events: list[MarketEvent], cutoff_ts: int) -> None:
    """Point-in-time guard: no event may post-date the decision cutoff."""
    if events and events[-1].ts > cutoff_ts:
        raise LeakageError(
            f"lookahead detected: event ts {events[-1].ts} > cutoff {cutoff_ts}"
        )


def derive_seed(base_seed: int, *parts: object) -> int:
    """Deterministically derive a child seed from a base seed and labels.

    Lets every experiment / fold get an independent but reproducible RNG stream.
    """
    blob = "|".join([str(base_seed), *map(str, parts)]).encode()
    return int(hashlib.sha256(blob).hexdigest()[:8], 16)


def dataset_fingerprint(ds: Dataset) -> str:
    """Stable content hash of a dataset's partition layout for provenance."""
    parts = []
    for p in Partition:
        b = ds.bounds(p)
        parts.append(f"{p.value}:{b.start_idx}:{b.end_idx}")
    blob = f"{ds.symbol}|{ds.n_events}|{'|'.join(parts)}".encode()
    return hashlib.sha256(blob).hexdigest()[:16]
