"""Tool registry: schema generation, arg validation, and holdout rejection."""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_research_agent.config import DataConfig, EvalConfig, SimConfig
from quant_research_agent.data import generate_synthetic
from quant_research_agent.models.base import ToolCall
from quant_research_agent.tools import default_registry
from quant_research_agent.tools.base import ToolContext
from quant_research_agent.tools.code_tool import WriteStrategyArgs, WriteStrategyTool
from quant_research_agent.tools.data_tool import DataSummaryArgs, DataSummaryTool


def _ctx(tmp_path: Path) -> ToolContext:
    ds = generate_synthetic(DataConfig(symbol="T", n_events=8_000), seed=1)
    return ToolContext(
        workspace=tmp_path,
        dataset=ds,
        sim_config=SimConfig(),
        eval_config=EvalConfig(),
        decision_interval_ns=20_000_000,
    )


def test_registry_emits_openai_schema() -> None:
    reg = default_registry()
    schema = reg.openai_schema()
    names = {s["function"]["name"] for s in schema}
    assert {"write_strategy", "run_backtest", "submit_strategy", "get_data_summary"} <= names
    for s in schema:
        assert s["type"] == "function"
        assert "parameters" in s["function"]


@pytest.mark.asyncio
async def test_write_strategy_requires_build(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    res = await WriteStrategyTool().run(
        WriteStrategyArgs(filename="bad.py", code="x = 1\n"), ctx
    )
    assert not res.ok
    assert "build" in res.content


@pytest.mark.asyncio
async def test_data_tool_blocks_holdout(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    res = await DataSummaryTool().run(DataSummaryArgs(partition="holdout"), ctx)
    assert not res.ok
    assert "holdout" in res.content.lower()


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(tmp_path: Path) -> None:
    reg = default_registry()
    ctx = _ctx(tmp_path)
    res = await reg.dispatch(ToolCall(id="x", name="does_not_exist", arguments={}), ctx)
    assert not res.ok


@pytest.mark.asyncio
async def test_data_summary_train_ok(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    res = await DataSummaryTool().run(DataSummaryArgs(partition="train"), ctx)
    assert res.ok
    assert res.data["n_events"] > 0
