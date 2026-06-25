"""High-level backtest entry point.

Selects the fastest available `SimCore` (native if built and preferred,
otherwise the Python reference) and runs a `Strategy` against a dataset slice.
"""

from __future__ import annotations

from collections.abc import Sequence

from quant_research_agent.config import SimConfig
from quant_research_agent.types import BacktestResult, MarketEvent

from .base import SimCore, StrategyFn
from .native import NativeSimCore, native_available
from .python_sim import PythonSimCore


def select_core(config: SimConfig) -> SimCore:
    if config.prefer_native and native_available():
        return NativeSimCore()
    return PythonSimCore()


class Backtester:
    def __init__(self, config: SimConfig, decision_interval_ns: int) -> None:
        self.config = config
        self.decision_interval_ns = decision_interval_ns
        self.core = select_core(config)

    @property
    def backend(self) -> str:
        return type(self.core).__name__

    def run(self, events: Sequence[MarketEvent], strategy: StrategyFn) -> BacktestResult:
        return self.core.run(events, strategy, self.config, self.decision_interval_ns)
