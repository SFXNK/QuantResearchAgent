"""FastAPI dashboard: run history, per-run results, and a strategy leaderboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .store import ExperimentStore

_STYLE = """
<style>
  body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem; color: #1c1c28; }
  h1, h2 { font-weight: 650; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { text-align: left; padding: 0.45rem 0.7rem; border-bottom: 1px solid #e6e6ef; font-size: 14px; }
  th { background: #f5f5fa; }
  .yes { color: #0a7d28; font-weight: 600; }
  .no { color: #9aa0aa; }
  a { color: #2b59ff; text-decoration: none; }
  .pill { background:#eef1ff; border-radius:10px; padding:2px 8px; font-size:12px; }
  code { background:#f5f5fa; padding:1px 5px; border-radius:5px; }
</style>
"""


def _fmt(x: object, nd: int = 3) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def create_app(db_path: str | Path) -> FastAPI:
    store = ExperimentStore(db_path)
    app = FastAPI(title="QuantResearchAgent Dashboard")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        runs = store.list_runs()
        rows = "".join(
            f"<tr><td><a href='/runs/{r['id']}'>#{r['id']}</a></td>"
            f"<td>{r['symbol']}</td><td>{r['model_name']}</td>"
            f"<td>{r['n_experiments']}</td>"
            f"<td>{_fmt(r['pbo'])}</td>"
            f"<td>{r['n_survivors']}</td>"
            f"<td>{_fmt(r['survival_rate'])}</td></tr>"
            for r in runs
        )
        lb = store.leaderboard()
        lb_rows = "".join(
            f"<tr><td>{e['strategy_name']}</td><td>{e['symbol']}</td>"
            f"<td>{_fmt(e['holdout_sharpe'])}</td><td>{_fmt(e['deflated_sr'])}</td>"
            f"<td>{_fmt(e['adjusted_pvalue'])}</td>"
            f"<td class='{'yes' if e['survived'] else 'no'}'>"
            f"{'survived' if e['survived'] else 'failed'}</td></tr>"
            for e in lb
        )
        return f"""
        <html><head><title>QuantResearchAgent</title>{_STYLE}</head><body>
        <h1>QuantResearchAgent</h1>
        <p class='pill'>a harness that resists fooling itself</p>
        <h2>Runs</h2>
        <table><tr><th>Run</th><th>Symbol</th><th>Model</th><th>Experiments</th>
        <th>PBO</th><th>Survivors</th><th>Survival rate</th></tr>{rows}</table>
        <h2>Strategy leaderboard (out-of-sample)</h2>
        <table><tr><th>Strategy</th><th>Symbol</th><th>Holdout Sharpe</th>
        <th>Deflated SR</th><th>Adj. p-value</th><th>Verdict</th></tr>{lb_rows}</table>
        </body></html>
        """

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_view(run_id: int) -> str:
        run = store.run(run_id)
        if run is None:
            return "<h1>Run not found</h1>"
        evals = store.evaluations_for(run_id)
        usage = store.usage_totals(run_id)
        rows = "".join(
            f"<tr><td>{e['strategy_name']}</td>"
            f"<td>{_fmt(e['holdout_sharpe'])}</td>"
            f"<td>{_fmt(e['max_drawdown'])}</td>"
            f"<td>{_fmt(e['deflated_sr'])}</td>"
            f"<td>{_fmt(e['pvalue'])}</td><td>{_fmt(e['adjusted_pvalue'])}</td>"
            f"<td>{_fmt(e['wf_frac_positive'])}</td>"
            f"<td class='{'yes' if e['survived'] else 'no'}'>"
            f"{'survived' if e['survived'] else 'failed'}</td></tr>"
            for e in evals
        )
        return f"""
        <html><head><title>Run #{run_id}</title>{_STYLE}</head><body>
        <p><a href='/'>&larr; all runs</a></p>
        <h1>Run #{run_id} &mdash; {run['symbol']}</h1>
        <p>Model: <code>{run['model_name']}</code> &middot; PBO:
        <b>{_fmt(run['pbo'])}</b> &middot; Survivors: <b>{run['n_survivors']}</b> /
        {run['n_experiments']} &middot; Best baseline Sharpe:
        {_fmt(run['best_baseline_sharpe'])}</p>
        <p>Tokens: {usage.get('p', 0):.0f}+{usage.get('c', 0):.0f} &middot;
        Cost: ${usage.get('cost', 0):.4f} &middot; LLM calls: {usage.get('calls', 0):.0f}
        (cache hits {usage.get('cached', 0):.0f})</p>
        <h2>Candidate evaluations (holdout)</h2>
        <table><tr><th>Strategy</th><th>Holdout Sharpe</th><th>Max DD</th>
        <th>Deflated SR</th><th>p-value</th><th>Adj. p</th><th>WF frac+</th>
        <th>Verdict</th></tr>{rows}</table>
        </body></html>
        """

    @app.get("/api/runs")
    def api_runs() -> list[dict]:
        return store.list_runs()

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: int) -> dict:
        return {
            "run": store.run(run_id),
            "evaluations": store.evaluations_for(run_id),
            "usage": store.usage_totals(run_id),
        }

    return app
