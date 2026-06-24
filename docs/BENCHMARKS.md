# Benchmarks

Reproduce with:

```bash
uv run python scripts/benchmark.py --events 200000 --repeat 5 --parallel 8 --parallel-tasks 32
```

## What is measured

- **events/sec** - market events replayed through the matching core per second.
- **backtests/sec** - single-core full-backtest rate at the configured event count.
- **backtests/hour (parallel)** - effective rate across N worker processes, i.e.
  the orchestrator's real throughput when running many experiments.

## The optimization: Python reference -> native C++ core

The Python `PythonSimCore` is the executable spec (clarity over speed). The
"after" is the native core (`sim_core/`), which keeps the hot replay loop in
C++ and reuses the engine's slab allocator. Crossing the Python/C++ boundary
only at decision points (not per tick) is what preserves the speedup.

| Core | M events/sec | backtests/sec | Notes |
|---|---|---|---|
| Python reference | _fill in_ | _fill in_ | clarity-first spec |
| Native (C++) | _fill in_ | _fill in_ | hot loop in C++, decision-point callbacks |
| **Speedup** | _fill in_ | | |

Parallel throughput (8 workers): _fill in_ backtests/hour.

> Record your machine's numbers here after running the benchmark. The values
> feed the resume headline (e.g. "N backtests/hour across parallel sandboxed
> rollouts; native core M x faster than the Python reference").

## Methodology notes

- Best-of-`repeat` wall time per core to reduce noise.
- Single asset/venue; decision interval 1s; synthetic Hawkes order flow.
- The native parity test (`tests/test_sim_parity.py`) guarantees the optimized
  core produces the same equity curve as the reference, so the speedup is not
  bought with a behavior change.
