"""Strategy loading + backtest execution.

Importable in-process *and* runnable as a module inside the sandbox:

    python -m quant_research_agent.research.runner --strategy strat.py \
        --events events.npz --sim-config sim.json --interval 1000000000 --out result.json

Keeping a single entrypoint guarantees the sandboxed run and the in-process run
execute identical code paths.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from quant_research_agent.config import SimConfig
from quant_research_agent.eval.metrics import Metrics, compute_metrics
from quant_research_agent.sim import Backtester
from quant_research_agent.strategy.base import Strategy, as_strategy_fn
from quant_research_agent.types import BacktestResult, EventType, MarketEvent, Side


def load_strategy(path: str | Path) -> Strategy:
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"af_strategy_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load strategy from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build"):
        raise AttributeError("strategy module must define build() -> Strategy")
    strategy = module.build()
    if not hasattr(strategy, "on_observation"):
        raise TypeError("build() must return an object with on_observation()")
    return strategy  # type: ignore[no-any-return]


def save_events(events: Sequence[MarketEvent], path: str | Path) -> None:
    n = len(events)
    np.savez_compressed(
        path,
        ts=np.fromiter((e.ts for e in events), dtype=np.int64, count=n),
        type=np.fromiter((int(e.type) for e in events), dtype=np.int8, count=n),
        side=np.fromiter((int(e.side) for e in events), dtype=np.int8, count=n),
        price=np.fromiter((e.price for e in events), dtype=np.int64, count=n),
        qty=np.fromiter((e.qty for e in events), dtype=np.int64, count=n),
        order_id=np.fromiter((e.order_id for e in events), dtype=np.int64, count=n),
    )


def load_events(path: str | Path) -> list[MarketEvent]:
    z = np.load(path)
    return [
        MarketEvent(
            int(z["ts"][i]),
            EventType(int(z["type"][i])),
            Side(int(z["side"][i])),
            int(z["price"][i]),
            int(z["qty"][i]),
            int(z["order_id"][i]),
        )
        for i in range(z["ts"].shape[0])
    ]


def run_backtest(
    strategy: Strategy,
    events: Sequence[MarketEvent],
    sim_config: SimConfig,
    decision_interval_ns: int,
) -> tuple[BacktestResult, Metrics]:
    bt = Backtester(sim_config, decision_interval_ns)
    result = bt.run(events, as_strategy_fn(strategy))
    metrics = compute_metrics(result.equity, result.returns, decision_interval_ns)
    return result, metrics


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--sim-config", required=True)
    parser.add_argument("--interval", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    sim_config = SimConfig.model_validate_json(Path(args.sim_config).read_text())
    strategy = load_strategy(args.strategy)
    events = load_events(args.events)
    result, metrics = run_backtest(strategy, events, sim_config, args.interval)

    out: dict[str, Any] = {
        "metrics": metrics.as_dict(),
        "n_trades": result.n_trades,
        "turnover": result.turnover,
        "final_position": result.final_position,
        "fees_paid": result.fees_paid,
        "equity": result.equity.tolist(),
        "returns": result.returns.tolist(),
    }
    Path(args.out).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
