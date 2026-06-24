"""Core value types shared across the harness.

These are deliberately plain and dependency-light so they can cross the
agent / sandbox / sim / eval boundaries (and, in spirit, the Python/C++ one)
without coupling layers together.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import numpy as np


class Side(enum.IntEnum):
    BUY = 0
    SELL = 1

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY

    @property
    def sign(self) -> int:
        """+1 for buy, -1 for sell (position delta direction)."""
        return 1 if self is Side.BUY else -1


class OrderType(enum.IntEnum):
    LIMIT = 0
    MARKET = 1


class EventType(enum.IntEnum):
    ADD = 0
    CANCEL = 1
    TRADE = 2


@dataclass(slots=True)
class MarketEvent:
    """A single timestamped event in the historical/synthetic order flow.

    Prices are integer ticks to match the underlying matching engine.
    `ts` is nanoseconds since the session start.
    """

    ts: int
    type: EventType
    side: Side
    price: int
    qty: int
    order_id: int = 0


@dataclass(slots=True)
class Fill:
    """A fill against one of *our* (the strategy's) orders."""

    ts: int
    order_id: int
    side: Side
    price: int
    qty: int
    is_maker: bool


@dataclass(slots=True)
class BacktestResult:
    """Output of a single backtest run.

    `equity` is the mark-to-market account value sampled at decision points.
    `returns` are the per-step simple returns derived from `equity`.
    """

    equity: np.ndarray
    returns: np.ndarray
    timestamps: np.ndarray
    n_trades: int
    turnover: float
    final_position: int
    fees_paid: float
    meta: dict[str, float] = field(default_factory=dict)

    @property
    def n_steps(self) -> int:
        return int(self.returns.shape[0])


class Partition(enum.Enum):
    """Time-ordered data partitions. Order matters: TRAIN < VALIDATION < HOLDOUT."""

    TRAIN = "train"
    VALIDATION = "validation"
    HOLDOUT = "holdout"

    @property
    def agent_accessible(self) -> bool:
        """HOLDOUT is never reachable through an agent-facing tool."""
        return self is not Partition.HOLDOUT
