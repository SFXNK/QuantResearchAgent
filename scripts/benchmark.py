"""Backtest throughput benchmark.

Measures:
- single-core events/sec and backtests/sec for the Python reference core and,
  if built, the native C++ core (the "before/after" optimization: moving the
  hot replay loop into C++);
- parallel backtests/hour across processes (the orchestrator's effective rate).

    python scripts/benchmark.py --events 200000 --repeat 5 --parallel 8
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor

from alphaforge.config import DataConfig, SimConfig
from alphaforge.data import generate_synthetic
from alphaforge.sim import Action, NativeSimCore, Observation, PythonSimCore, native_available
from alphaforge.types import MarketEvent, Partition, Side


def _strategy(obs: Observation) -> list[Action]:
    if obs.best_bid is None or obs.best_ask is None:
        return []
    if obs.step % 7 == 0:
        return [Action.market(Side.BUY, 1)]
    if obs.step % 7 == 3:
        return [Action.market(Side.SELL, 1)]
    return []


def _events(n: int) -> list[MarketEvent]:
    ds = generate_synthetic(DataConfig(symbol="BENCH", n_events=n), seed=0)
    return ds.partition_events(Partition.TRAIN)


def _time_core(core, events, interval, repeat: int) -> tuple[float, float]:  # noqa: ANN001
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        core.run(events, _strategy, SimConfig(), interval)
        best = min(best, time.perf_counter() - t0)
    events_per_s = len(events) / best
    backtests_per_s = 1.0 / best
    return events_per_s, backtests_per_s


def _worker(n: int) -> float:
    events = _events(n)
    t0 = time.perf_counter()
    PythonSimCore().run(events, _strategy, SimConfig(), 1_000_000_000)
    return time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=200_000)
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--parallel-tasks", type=int, default=32)
    args = ap.parse_args()

    events = _events(args.events)
    interval = 1_000_000_000

    print(f"events: {len(events)}  repeat: {args.repeat}")
    eps, bps = _time_core(PythonSimCore(), events, interval, args.repeat)
    print(f"[python] {eps / 1e6:.3f} M events/s | {bps:.2f} backtests/s")

    if native_available():
        neps, nbps = _time_core(NativeSimCore(), events, interval, args.repeat)
        print(f"[native] {neps / 1e6:.3f} M events/s | {nbps:.2f} backtests/s")
        print(f"[native] speedup vs python: {neps / eps:.1f}x")
    else:
        print("[native] not built (build sim_core/ for the optimized path)")

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(_worker, [args.events] * args.parallel_tasks))
    elapsed = time.perf_counter() - t0
    rate_hr = args.parallel_tasks / elapsed * 3600
    print(
        f"[parallel x{args.parallel}] {args.parallel_tasks} backtests in {elapsed:.2f}s "
        f"-> {rate_hr:,.0f} backtests/hour"
    )


if __name__ == "__main__":
    main()
