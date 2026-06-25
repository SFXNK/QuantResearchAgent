"""Strategy interface.

A strategy is a small object exposing `on_observation(obs) -> list[Action]`.
The agent writes these as standalone modules that define a `build()` factory
returning a `Strategy`; the harness imports that factory inside the sandbox.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from quant_research_agent.sim.base import Action, Observation


@runtime_checkable
class Strategy(Protocol):
    name: str

    def on_observation(self, obs: Observation) -> Sequence[Action]: ...


def as_strategy_fn(strategy: Strategy):  # noqa: ANN201 - returns a StrategyFn
    """Adapt a `Strategy` object to the bare `StrategyFn` the sim core expects."""

    def _fn(obs: Observation) -> Sequence[Action]:
        return strategy.on_observation(obs)

    return _fn
