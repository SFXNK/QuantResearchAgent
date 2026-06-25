"""Central configuration objects.

All randomness flows from `seed`; all paths flow from `QuantResearchAgentConfig` so a
run is fully described by one serializable object (reproducibility requirement).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class SimConfig(BaseModel):
    """Market-simulation parameters."""

    tick_size: float = 0.01
    max_price_levels: int = 100_000
    latency_ns: int = 1_000_000  # 1ms strategy->exchange latency
    maker_fee_bps: float = -0.5  # rebate
    taker_fee_bps: float = 1.0
    impact_coeff: float = 0.1  # linear temporary impact per unit qty (ticks)
    prefer_native: bool = True  # use compiled C++ core when available


class DataConfig(BaseModel):
    symbol: str = "SYNTH"
    source: str = "synthetic"  # "synthetic" | "crypto_l2"
    path: str | None = None  # CSV/Parquet file for crypto_l2 source
    tick_size: float = 0.01  # price->tick mapping for crypto_l2 (match SimConfig.tick_size)
    n_events: int = 200_000
    train_frac: float = 0.5
    val_frac: float = 0.25
    # holdout_frac is the remainder
    embargo_frac: float = 0.01  # gap between partitions to prevent leakage
    # Decision cadence. The synthetic generator advances ~1ms per emitted batch,
    # so a 20ms cadence yields hundreds of decision points across the data.
    decision_interval_ns: int = 20_000_000  # 20ms bars at decision points


class AgentConfig(BaseModel):
    max_steps: int = 24
    max_refine_iters: int = 5
    context_token_budget: int = 24_000
    journal_max_entries: int = 50
    temperature: float = 0.7


class SandboxConfig(BaseModel):
    backend: str = "auto"  # "auto" | "docker" | "local"
    image: str = "python:3.12-slim"
    cpu_limit: float = 1.0
    memory_mb: int = 1024
    pids_limit: int = 128
    wall_timeout_s: int = 60
    network_disabled: bool = True


class EvalConfig(BaseModel):
    walk_forward_windows: int = 4
    cv_folds: int = 6
    cv_embargo_frac: float = 0.01
    cscv_partitions: int = 8  # S for combinatorially-symmetric CV (must be even)
    fdr_alpha: float = 0.05
    n_baseline_bootstrap: int = 1000


class ModelConfig(BaseModel):
    provider: str = "echo"  # "echo" | "ollama" | "openai" | "anthropic"
    model: str = "echo"
    base_url: str | None = None
    api_key_env: str | None = None
    max_tokens: int = 2048
    request_timeout_s: float = 120.0
    max_retries: int = 4


class QuantResearchAgentConfig(BaseModel):
    seed: int = 1
    run_dir: Path = Field(default=Path("runs"))
    db_path: Path = Field(default=Path("runs/quant_research_agent.sqlite"))
    n_experiments: int = 8
    max_parallel: int = 4
    use_sandbox: bool = False  # run agent backtests inside the hardened sandbox

    sim: SimConfig = Field(default_factory=SimConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)

    def holdout_frac(self) -> float:
        return max(0.0, 1.0 - self.data.train_frac - self.data.val_frac)
