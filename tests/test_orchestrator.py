"""Full-pipeline test: orchestrator -> experiments -> OOS eval -> persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_research_agent.config import AgentConfig, QuantResearchAgentConfig, DataConfig, ModelConfig
from quant_research_agent.obs.store import ExperimentStore
from quant_research_agent.orchestrator import Orchestrator
from quant_research_agent.report import generate_markdown_report


@pytest.mark.asyncio
async def test_full_run_persists_and_reports(tmp_path: Path) -> None:
    cfg = QuantResearchAgentConfig(
        seed=3,
        run_dir=tmp_path,
        db_path=tmp_path / "af.sqlite",
        n_experiments=4,
        max_parallel=2,
        use_sandbox=False,
        data=DataConfig(symbol="T", n_events=20_000),
        agent=AgentConfig(max_steps=10),
        model=ModelConfig(provider="echo", model="echo"),
    )
    summary = await Orchestrator(cfg).run()

    assert summary.n_submitted >= 1
    assert summary.report.n_candidates == summary.n_submitted
    assert 0.0 <= summary.report.survival_rate <= 1.0

    store = ExperimentStore(cfg.db_path)
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["n_experiments"] == 4

    evals = store.evaluations_for(summary.run_id)
    assert len(evals) == summary.n_submitted

    md = generate_markdown_report(store, summary.run_id)
    assert "QuantResearchAgent run" in md
    assert "PBO" in md

    # cost must be zero on the offline echo model
    assert summary.ledger["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_response_cache_makes_rerun_free(tmp_path: Path) -> None:
    cfg = QuantResearchAgentConfig(
        seed=3,
        run_dir=tmp_path,
        db_path=tmp_path / "af.sqlite",
        n_experiments=2,
        max_parallel=2,
        data=DataConfig(symbol="T", n_events=12_000),
        agent=AgentConfig(max_steps=10),
        model=ModelConfig(provider="echo", model="echo"),
    )
    first = await Orchestrator(cfg).run()
    second = await Orchestrator(cfg).run()
    # Second run should hit the prompt cache for identical prompts.
    assert second.ledger["cache_hits"] >= first.ledger["cache_hits"]
