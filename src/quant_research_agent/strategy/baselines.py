"""Baseline strategies.

These are the bar every agent-generated strategy must clear on the holdout
before it is reported as "surviving". Random and flat baselines also calibrate
the multiple-testing null distribution.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from quant_research_agent.sim.base import Action, Observation
from quant_research_agent.types import Side


class FlatStrategy:
    """Does nothing. The true zero-skill baseline."""

    name = "flat"

    def on_observation(self, obs: Observation) -> Sequence[Action]:
        return ()


class BuyAndHold:
    """Buy one unit on the first observation, then hold."""

    name = "buy_and_hold"

    def __init__(self) -> None:
        self._entered = False

    def on_observation(self, obs: Observation) -> Sequence[Action]:
        if not self._entered and obs.best_ask is not None:
            self._entered = True
            return (Action.market(Side.BUY, 1),)
        return ()


class RandomTrader:
    """Random market orders. Used to build the null distribution of Sharpe."""

    name = "random"

    def __init__(self, seed: int = 0, trade_prob: float = 0.1, max_pos: int = 5) -> None:
        self._rng = np.random.default_rng(seed)
        self._p = trade_prob
        self._max_pos = max_pos

    def on_observation(self, obs: Observation) -> Sequence[Action]:
        if obs.best_bid is None or obs.best_ask is None:
            return ()
        if self._rng.random() > self._p:
            return ()
        buy = self._rng.random() < 0.5
        if buy and obs.position < self._max_pos:
            return (Action.market(Side.BUY, 1),)
        if not buy and obs.position > -self._max_pos:
            return (Action.market(Side.SELL, 1),)
        return ()


class MovingAverageCross:
    """Classic momentum: go long when fast MA > slow MA of the mid, else flat/short."""

    name = "ma_cross"

    def __init__(self, fast: int = 8, slow: int = 32, max_pos: int = 3) -> None:
        self.fast = fast
        self.slow = slow
        self._max_pos = max_pos
        self._mids: list[float] = []

    def on_observation(self, obs: Observation) -> Sequence[Action]:
        mid = obs.mid
        if mid is None:
            return ()
        self._mids.append(mid)
        if len(self._mids) < self.slow:
            return ()
        arr = np.asarray(self._mids[-self.slow :])
        fast_ma = float(arr[-self.fast :].mean())
        slow_ma = float(arr.mean())
        want = 1 if fast_ma > slow_ma else -1
        delta = want * self._max_pos - obs.position
        if delta > 0:
            return (Action.market(Side.BUY, min(delta, 1)),)
        if delta < 0:
            return (Action.market(Side.SELL, min(-delta, 1)),)
        return ()


def baseline_strategies(seed: int = 0) -> list:
    return [FlatStrategy(), BuyAndHold(), RandomTrader(seed=seed), MovingAverageCross()]
