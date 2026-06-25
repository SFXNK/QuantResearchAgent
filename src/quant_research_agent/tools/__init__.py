"""Typed, schema-generating research tools."""

from .backtest_tool import RunBacktestTool, SubmitStrategyTool
from .base import Tool, ToolContext, ToolResult
from .code_tool import ReadStrategyTool, WriteStrategyTool
from .data_tool import DataSummaryTool
from .metrics_tool import ComputeMetricsTool
from .registry import ToolRegistry


def default_registry() -> ToolRegistry:
    """The standard research toolset exposed to the agent."""
    return ToolRegistry(
        [
            DataSummaryTool(),
            WriteStrategyTool(),
            ReadStrategyTool(),
            RunBacktestTool(),
            ComputeMetricsTool(),
            SubmitStrategyTool(),
        ]
    )


__all__ = [
    "ComputeMetricsTool",
    "DataSummaryTool",
    "ReadStrategyTool",
    "RunBacktestTool",
    "SubmitStrategyTool",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "WriteStrategyTool",
    "default_registry",
]
