"""Headline report generation from the experiment store."""

from __future__ import annotations

from pathlib import Path

from alphaforge.obs.store import ExperimentStore


def _num(x: object, default: float = float("nan")) -> float:
    try:
        v = float(x)  # type: ignore[arg-type]
        return v
    except (TypeError, ValueError):
        return default


def generate_markdown_report(store: ExperimentStore, run_id: int) -> str:
    run = store.run(run_id)
    if run is None:
        return f"# Run {run_id} not found"
    evals = store.evaluations_for(run_id)
    usage = store.usage_totals(run_id)
    survivors = [e for e in evals if e["survived"]]

    lines = [
        f"# Alphaforge run #{run_id} - {run['symbol']}",
        "",
        f"- Model: `{run['model_name']}` ({run['model_provider']})",
        f"- Experiments: {run['n_experiments']}",
        f"- Candidates evaluated out-of-sample: {len(evals)}",
        f"- **Survivors (beat baselines + corrected significance + deflated SR >= 0.95): "
        f"{run['n_survivors']} ({_num(run['survival_rate']) * 100:.1f}%)**",
        f"- Probability of Backtest Overfitting (PBO): {_num(run['pbo']):.3f}",
        f"- Best baseline holdout Sharpe: {_num(run['best_baseline_sharpe']):.3f}",
        f"- LLM cost: ${usage.get('cost', 0):.4f} over {int(usage.get('calls', 0))} calls "
        f"({int(usage.get('cached', 0))} cache hits)",
        "",
        "## The honest headline",
        "",
        f"Of {len(evals)} agent-generated strategies, **{len(survivors)} survived** the held-out "
        "test after multiple-testing correction. Most do not survive - that is the point: the "
        "harness measures generalization, not in-sample luck.",
        "",
        "## Candidate results (holdout)",
        "",
        "| Strategy | Holdout Sharpe | Max DD | Deflated SR | Adj. p | WF frac+ | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in evals:
        verdict = "SURVIVED" if e["survived"] else "failed"
        lines.append(
            f"| {e['strategy_name']} | {e['holdout_sharpe']:.3f} | {e['max_drawdown']:.3f} | "
            f"{e['deflated_sr']:.3f} | {e['adjusted_pvalue']:.3f} | "
            f"{e['wf_frac_positive']:.2f} | {verdict} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_report(store: ExperimentStore, run_id: int, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(generate_markdown_report(store, run_id))
    return out_path
