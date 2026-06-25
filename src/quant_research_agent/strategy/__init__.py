"""Strategy interface + baselines."""

from .base import Strategy, as_strategy_fn
from .baselines import (
    BuyAndHold,
    FlatStrategy,
    MovingAverageCross,
    RandomTrader,
    baseline_strategies,
)

__all__ = [
    "BuyAndHold",
    "FlatStrategy",
    "MovingAverageCross",
    "RandomTrader",
    "Strategy",
    "as_strategy_fn",
    "baseline_strategies",
]
