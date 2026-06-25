"""The `SimCore` boundary.

A strategy never touches the matching engine directly. It receives an
`Observation` at each decision point and returns a list of `Action`s. This is
the only contract the agent-written code depends on, and it is identical for
the native (C++) and pure-Python simulators so the two can be checked for
parity.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from quant_research_agent.config import SimConfig
from quant_research_agent.types import BacktestResult, MarketEvent, Side


class ActionKind(enum.IntEnum):
    LIMIT = 0
    MARKET = 1
    CANCEL = 2


@dataclass(slots=True)
class Observation:
    """What the strategy sees at a decision point. No future information."""

    step: int
    ts: int
    best_bid: int | None
    best_ask: int | None
    position: int
    cash: float
    equity: float

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> int | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


@dataclass(slots=True)
class Action:
    kind: ActionKind
    side: Side = Side.BUY
    price: int = 0
    qty: int = 0
    order_id: int = 0

    @staticmethod
    def limit(side: Side, price: int, qty: int, order_id: int) -> Action:
        return Action(ActionKind.LIMIT, side, price, qty, order_id)

    @staticmethod
    def market(side: Side, qty: int) -> Action:
        return Action(ActionKind.MARKET, side, 0, qty, 0)

    @staticmethod
    def cancel(order_id: int) -> Action:
        return Action(ActionKind.CANCEL, Side.BUY, 0, 0, order_id)


# A strategy is any callable mapping an observation to desired actions.
StrategyFn = Callable[[Observation], Sequence[Action]]


@runtime_checkable
class SimCore(Protocol):
    """Event-driven market simulator contract."""

    def run(
        self,
        events: Sequence[MarketEvent],
        strategy: StrategyFn,
        config: SimConfig,
        decision_interval_ns: int,
    ) -> BacktestResult: ...
