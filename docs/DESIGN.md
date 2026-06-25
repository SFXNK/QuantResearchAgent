# QuantResearchAgent Design

## 1. Problem & thesis

Automated "alpha discovery" is mostly a generator of false positives. An LLM
that can write and test strategies will, given enough attempts, produce
backtests that look spectacular and generalize to nothing. The interesting
engineering problem is therefore **not** "can an agent find a strategy?" but
**"can a harness let an agent search aggressively while remaining statistically
honest about what it found?"**

QuantResearchAgent is built around that thesis. Every design decision favors
*integrity of the measurement* over *impressiveness of the result*.

## 2. Component overview

| Layer | Package | Responsibility |
|------|---------|----------------|
| Sim core | `sim_core/` (C++) + `quant_research_agent.sim` | Event-driven market simulation, realistic fills, portfolio/PnL |
| Data | `quant_research_agent.data` | Partitioned, point-in-time datasets; synthetic + crypto L2 sources |
| Strategy | `quant_research_agent.strategy` | Strategy interface + baselines |
| Agent | `quant_research_agent.agent` | Research loop, journal memory, context budgeting |
| Tools | `quant_research_agent.tools` | Typed, schema-generating tools the agent calls |
| Sandbox | `quant_research_agent.sandbox` | Hardened isolated execution of agent code |
| Eval | `quant_research_agent.eval` | Metrics, walk-forward, purged CV, PBO, multiple-testing |
| Models | `quant_research_agent.models` | Provider-agnostic model gateway + cache |
| Obs | `quant_research_agent.obs` | Experiment store, tracing, cost ledger, dashboard |
| Control | `quant_research_agent.orchestrator`, `quant_research_agent.cli` | Parallel experiment orchestration + CLI |

## 3. The sim core (extending HFTMatchingEngine)

The original engine (`OrderBook`) is a deterministic, single-threaded,
price-time-priority matching engine with integer-tick prices and an
`OnTradeCallback` fill hook. We reuse it unchanged (vendored as a submodule)
and add, in `sim_core/`:

1. **A timestamp-ordered event loop** (`MarketSimulator`). It consumes a stream
   of timestamped `MarketEvent`s (add/cancel/trade from historical or synthetic
   flow) and interleaves the strategy's own orders by timestamp + a configurable
   latency.
2. **Market orders.** The original `OrderType::Market` enum is unimplemented;
   the simulator walks the opposite book to fill marketable quantity.
3. **A queue-position fill model.** A strategy's resting limit order only fills
   after the volume ahead of it at that price has traded. We track each of the
   agent's orders' queue position from book + trade events, the part naive
   vectorized backtesters get wrong.
4. **A portfolio/PnL layer** (`Portfolio`). Position, cash, fees, realized and
   unrealized PnL, computed from the fill callback.

The hot replay loop stays in C++. Python receives results at *decision points*
(bar/event granularity) rather than per tick, so the Python/C++ boundary is not
crossed millions of times per backtest.

### Fallback

`quant_research_agent.sim` exposes a `SimCore` protocol with two implementations:
`NativeSimCore` (the compiled C++ module) and `PythonSimCore` (a pure-Python
reference). The Python implementation is the executable spec and lets the whole
stack run with no native build. Tests assert the two agree.

## 4. Leakage & integrity model

Leakage is prevented structurally, not by convention:

- **Partitioning.** `data` splits every dataset into `TRAIN`, `VALIDATION`,
  `HOLDOUT` along the time axis with an embargo gap between partitions.
- **Tool-level enforcement.** The agent's data-access tool can *only* return
  `TRAIN`/`VALIDATION` rows. `HOLDOUT` is unreachable through any agent tool.
- **Network-deny sandbox.** Agent code runs with networking disabled, so it
  cannot fetch future data or exfiltrate the holdout.
- **Point-in-time access.** Data requests are `as_of`-bounded; a request at
  time `t` cannot observe rows with timestamp `> t`.
- **Holdout run by the harness.** Only the final, frozen strategy artifact is
  evaluated on `HOLDOUT`, by the orchestrator, never inside the agent loop.

## 5. Evaluation protocol

For each candidate strategy:

1. **In-sample fit** on `TRAIN`.
2. **Walk-forward** validation on `VALIDATION` (rolling/anchored windows).
3. **Purged + embargoed k-fold CV** to avoid label leakage across adjacent time
   folds (Lopez de Prado).
4. **Holdout** evaluation, once, by the harness.

Across the *whole population* of agent-generated strategies we then compute:

- **PBO** (Probability of Backtest Overfitting) via combinatorially-symmetric
  cross-validation (CSCV).
- **Deflated Sharpe Ratio**, correcting the observed Sharpe for the number of
  trials, skew, and kurtosis.
- **Multiple-testing correction** (Benjamini-Hochberg FDR / Bonferroni) on the
  per-strategy significance of holdout returns vs baselines.

A strategy is reported as "surviving" only if it beats baselines on holdout and
clears the corrected significance threshold.

## 6. Reproducibility

- Deterministic, seeded simulation and data generation.
- Every experiment row in the store records: hypothesis text, strategy code
  hash, full config, RNG seeds, model + prompt-cache key, and all metrics.
- Model responses cached by prompt hash; a re-run with the same seeds and cache
  reproduces results bit-for-bit.

## 7. Non-goals

- Real-money trading or order routing.
- Multi-venue / cross-asset portfolio optimization (single-asset, single-venue
  first; eval rigor matters more than market breadth).
- Beating the market. The deliverable is the *harness and the honest number*.
