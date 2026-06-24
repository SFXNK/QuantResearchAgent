"""Market-simulation layer: a stable `SimCore` boundary with native + Python cores."""

from .backtester import Backtester, select_core
from .base import Action, ActionKind, Observation, SimCore, StrategyFn
from .native import NativeSimCore, native_available
from .python_sim import PythonSimCore

__all__ = [
    "Action",
    "ActionKind",
    "Backtester",
    "NativeSimCore",
    "Observation",
    "PythonSimCore",
    "SimCore",
    "StrategyFn",
    "native_available",
    "select_core",
]
