# Resume bullets (Alphaforge)

Drop-in bullets for an "agent harness engineer" profile. Fill the `__` blanks
after running `scripts/benchmark.py` and a real research run. Keep the honesty
framing: the headline is *survival rate after correction*, not raw returns.

## Project entry

**Alphaforge - Autonomous Quant-Research Agent Harness** | Python, C++20, nanobind, Docker, asyncio, FastAPI

- Built a provider-agnostic **agent harness** (model gateway, typed tool
  protocol with auto-generated JSON schemas, context/token budgeting, and a
  bounded tool-calling loop) that drives an LLM through a full quant-research
  cycle: hypothesis -> strategy code -> sandboxed backtest -> refine -> submit.
- Engineered an **event-driven market simulator in C++20** that extends a
  price-time-priority matching engine with a timestamp-ordered event loop,
  market orders, a **queue-position fill model**, and a portfolio/PnL layer;
  exposed it to Python via **nanobind**, reaching __ M events/sec and a __x
  speedup over the Python reference (parity-tested for identical results).
- Designed a **leakage-resistant evaluation protocol**: structural train/val/
  **holdout** partitioning with embargo, point-in-time data access, and a
  network-denied execution sandbox that doubles as a data-leakage guard.
- Implemented rigorous **overfitting statistics** - Probability of Backtest
  Overfitting (CSCV), Deflated Sharpe Ratio, and Benjamini-Hochberg
  multiple-testing correction across the agent-generated population - so the
  headline metric is honest: __ of __ strategies survived out-of-sample after
  correction (PBO = __).
- Hardened the execution sandbox with **defense in depth** (non-root, dropped
  capabilities, seccomp profile, cgroup CPU/memory/PID limits, read-only rootfs,
  no-new-privileges) and proved containment with a security test suite (OOM,
  fork/thread bombs, CPU timeouts, network egress).
- Shipped the supporting infra: OpenAI/Anthropic/Ollama adapters with retries,
  rate-limiting and a **prompt-hash cache** (free, deterministic re-runs);
  SQLite experiment store; OpenTelemetry tracing; cost/token ledger; and a
  FastAPI dashboard with a strategy leaderboard. Ran on a free offline model in
  CI for $0.

## One-liner (if space-constrained)

- Built **Alphaforge**, an autonomous quant-research agent harness: an LLM tool
  loop over a **C++ event-driven market simulator** (nanobind) with a
  leakage-resistant, overfitting-aware (PBO / Deflated Sharpe / FDR) holdout
  evaluation - reporting that only __% of agent-generated strategies survive
  out of sample.

## Talking points (interview)

- Why queue-position fills matter and how the C++ engine's FIFO price-time
  matching makes them fall out naturally.
- Why the network-deny sandbox is simultaneously a security and a data-integrity
  control.
- Why generating many strategies *requires* PBO + multiple-testing correction,
  and what the deflated Sharpe ratio corrects for.
- The Python-reference-vs-native parity test as a contract for the optimization.
