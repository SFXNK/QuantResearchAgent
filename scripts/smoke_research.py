"""Minimal end-to-end demo (offline echo model, $0).

    python scripts/smoke_research.py

Runs a handful of experiments on synthetic data, evaluates out-of-sample, and
prints the honest headline. Use the CLI (`quant_research_agent research`) for full control.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from quant_research_agent.config import AgentConfig, QuantResearchAgentConfig, DataConfig, ModelConfig
from quant_research_agent.orchestrator import Orchestrator


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quant_research_agent_smoke_"))
    cfg = QuantResearchAgentConfig(
        seed=7,
        run_dir=tmp,
        db_path=tmp / "af.sqlite",
        n_experiments=6,
        max_parallel=3,
        data=DataConfig(symbol="SYNTH", n_events=40_000),
        agent=AgentConfig(max_steps=10),
        model=ModelConfig(provider="echo", model="echo"),
    )
    summary = await Orchestrator(cfg).run()
    r = summary.report
    print(f"\nRun #{summary.run_id} on {summary.dataset_symbol}")
    print(f"  submitted        : {summary.n_submitted}")
    print(f"  survivors        : {r.n_survivors} ({r.survival_rate * 100:.1f}%)")
    print(f"  PBO              : {r.pbo:.3f}")
    print(f"  best baseline SR : {r.best_baseline_sharpe:.3f}")
    print(f"  llm cost (USD)   : {summary.ledger['cost_usd']:.4f}")
    print(f"\nArtifacts in: {tmp}")


if __name__ == "__main__":
    asyncio.run(main())
