"""Partitioned, point-in-time dataset.

A `Dataset` is an immutable, time-sorted event stream split into TRAIN /
VALIDATION / HOLDOUT partitions with an embargo gap between them. Two
properties are enforced *structurally* rather than by convention:

1. Point-in-time: `as_of(p, t)` never returns an event with ``ts > t``.
2. Holdout isolation: there is no code path from an agent-facing tool to the
   HOLDOUT partition (the tools in `quant_research_agent.tools` only ever request
   TRAIN/VALIDATION; see `LeakageError`).
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass

from quant_research_agent.types import MarketEvent, Partition


class LeakageError(RuntimeError):
    """Raised when code attempts to read a forbidden partition or future data."""


@dataclass(frozen=True, slots=True)
class PartitionBounds:
    start_idx: int
    end_idx: int  # exclusive

    def __len__(self) -> int:
        return self.end_idx - self.start_idx


class Dataset:
    def __init__(
        self,
        events: Sequence[MarketEvent],
        symbol: str,
        bounds: dict[Partition, PartitionBounds],
    ) -> None:
        self._events: list[MarketEvent] = list(events)
        self.symbol = symbol
        self._bounds = bounds
        self._ts = [e.ts for e in self._events]

    @property
    def n_events(self) -> int:
        return len(self._events)

    def bounds(self, p: Partition) -> PartitionBounds:
        return self._bounds[p]

    def partition_events(self, p: Partition) -> list[MarketEvent]:
        b = self._bounds[p]
        return self._events[b.start_idx : b.end_idx]

    def as_of(self, p: Partition, ts: int) -> list[MarketEvent]:
        """All events in partition ``p`` with timestamp <= ``ts`` (no lookahead)."""
        b = self._bounds[p]
        lo, hi = b.start_idx, b.end_idx
        # rightmost index in [lo, hi) with ts <= the cutoff
        cut = bisect.bisect_right(self._ts, ts, lo, hi)
        return self._events[lo:cut]

    def partition_time_range(self, p: Partition) -> tuple[int, int]:
        evs = self.partition_events(p)
        if not evs:
            return (0, 0)
        return (evs[0].ts, evs[-1].ts)

    def agent_events(self, p: Partition) -> list[MarketEvent]:
        """Partition access for agent tools; HOLDOUT is forbidden here."""
        if not p.agent_accessible:
            raise LeakageError(
                f"Partition {p.value!r} is not accessible to the agent (holdout isolation)."
            )
        return self.partition_events(p)
