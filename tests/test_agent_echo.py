"""End-to-end agent loop on the offline echo model (no network, deterministic)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_research_agent.agent import ResearchAgent
from quant_research_agent.config import AgentConfig, DataConfig, EvalConfig, ModelConfig, SimConfig
from quant_research_agent.data import generate_synthetic
from quant_research_agent.models.gateway import ModelGateway
from quant_research_agent.tools import default_registry
from quant_research_agent.tools.base import ToolContext


@pytest.mark.asyncio
async def test_agent_completes_and_submits(tmp_path: Path) -> None:
    ds = generate_synthetic(DataConfig(symbol="T", n_events=15_000), seed=5)
    gateway = ModelGateway(ModelConfig(provider="echo", model="echo"))
    registry = default_registry()
    ctx = ToolContext(
        workspace=tmp_path,
        dataset=ds,
        sim_config=SimConfig(),
        eval_config=EvalConfig(),
        decision_interval_ns=1_000_000_000,
    )
    agent = ResearchAgent(gateway, registry, AgentConfig(max_steps=12))
    result = await agent.run(ctx)

    assert result.submitted is True
    assert result.strategy_path is not None
    assert result.strategy_path.exists()
    assert result.final_val_metrics is not None
    assert "sharpe" in result.final_val_metrics
    assert result.total_tokens > 0


@pytest.mark.asyncio
async def test_distinct_strategies_across_experiments(tmp_path: Path) -> None:
    """Echo derives strategy params from the prompt; different symbols -> different code."""
    gateway = ModelGateway(ModelConfig(provider="echo", model="echo"))
    codes = set()
    for sym in ("AAA", "BBB", "CCC"):
        ds = generate_synthetic(DataConfig(symbol=sym, n_events=12_000), seed=1)
        ctx = ToolContext(
            workspace=tmp_path / sym,
            dataset=ds,
            sim_config=SimConfig(),
            eval_config=EvalConfig(),
            decision_interval_ns=1_000_000_000,
        )
        ctx.workspace.mkdir(parents=True)
        agent = ResearchAgent(gateway, default_registry(), AgentConfig(max_steps=12))
        result = await agent.run(ctx)
        assert result.strategy_path is not None
        codes.add(result.strategy_path.read_text())
    assert len(codes) >= 2
