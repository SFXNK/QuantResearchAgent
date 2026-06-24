"""Alphaforge command-line interface."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from alphaforge.config import (
    AgentConfig,
    AlphaforgeConfig,
    DataConfig,
    ModelConfig,
    SandboxConfig,
)
from alphaforge.obs.store import ExperimentStore
from alphaforge.orchestrator import Orchestrator
from alphaforge.report import generate_markdown_report, write_report

app = typer.Typer(add_completion=False, help="Alphaforge: autonomous quant-research agent harness.")
console = Console()


def _infer_provider(model: str, provider: str | None) -> str:
    if provider:
        return provider
    if model == "echo":
        return "echo"
    if ":" in model:  # ollama tags look like 'qwen2.5-coder:7b'
        return "ollama"
    if model.startswith("claude"):
        return "anthropic"
    return "openai"


@app.command()
def research(
    experiments: int = typer.Option(8, help="Number of research experiments."),
    model: str = typer.Option("echo", help="Model name (echo|ollama tag|gpt-*|claude-*)."),
    provider: str = typer.Option(None, help="Override provider (echo|ollama|openai|anthropic)."),
    base_url: str = typer.Option(
        None, help="Override API base URL, e.g. https://www.packyapi.com/v1 for a proxy."
    ),
    api_key_env: str = typer.Option(
        None, help="Env var holding the API key (default OPENAI_API_KEY / ANTHROPIC_API_KEY)."
    ),
    seed: int = typer.Option(1, help="Master seed."),
    max_parallel: int = typer.Option(4, help="Max concurrent experiments."),
    n_events: int = typer.Option(200_000, help="Synthetic event count."),
    symbol: str = typer.Option("SYNTH", help="Symbol label."),
    data_source: str = typer.Option("synthetic", help="synthetic | crypto_l2."),
    data_path: str = typer.Option(None, help="CSV/Parquet file for crypto_l2 source."),
    tick_size: float = typer.Option(0.01, help="Price->tick size for crypto_l2 (match sim)."),
    sandbox: bool = typer.Option(False, help="Run agent backtests in the hardened sandbox."),
    run_dir: Path = typer.Option(Path("runs"), help="Run artifact directory."),
    db: Path = typer.Option(Path("runs/alphaforge.sqlite"), help="Experiment DB path."),
) -> None:
    """Run the autonomous research loop and the out-of-sample evaluation."""
    cfg = AlphaforgeConfig(
        seed=seed,
        run_dir=run_dir,
        db_path=db,
        n_experiments=experiments,
        max_parallel=max_parallel,
        use_sandbox=sandbox,
        data=DataConfig(
            symbol=symbol,
            source=data_source,
            path=data_path,
            tick_size=tick_size,
            n_events=n_events,
        ),
        agent=AgentConfig(),
        model=ModelConfig(
            provider=_infer_provider(model, provider),
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
        ),
        sandbox=SandboxConfig(backend="auto" if sandbox else "local"),
    )

    summary = asyncio.run(Orchestrator(cfg).run())
    report = summary.report

    table = Table(title=f"Run #{summary.run_id} - {summary.dataset_symbol}")
    table.add_column("Strategy")
    table.add_column("Holdout Sharpe", justify="right")
    table.add_column("Deflated SR", justify="right")
    table.add_column("Adj. p", justify="right")
    table.add_column("Verdict")
    for e in sorted(report.evaluations, key=lambda x: x.holdout_metrics.sharpe, reverse=True):
        table.add_row(
            e.candidate.name,
            f"{e.holdout_metrics.sharpe:.3f}",
            f"{e.deflated_sr:.3f}",
            f"{e.adjusted_pvalue:.3f}",
            "[green]SURVIVED[/green]" if e.survived else "[dim]failed[/dim]",
        )
    console.print(table)
    console.print(
        f"Submitted: {summary.n_submitted} | Survivors: {report.n_survivors} "
        f"({report.survival_rate * 100:.1f}%) | PBO: {report.pbo:.3f} | "
        f"Cost: ${summary.ledger['cost_usd']:.4f}"
    )

    report_path = write_report(
        ExperimentStore(db), summary.run_id, run_dir / f"report_run_{summary.run_id}.md"
    )
    console.print(f"Report written to [bold]{report_path}[/bold]")


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    db: Path = typer.Option(Path("runs/alphaforge.sqlite")),
) -> None:
    """Launch the results dashboard."""
    import uvicorn

    from alphaforge.obs.dashboard import create_app

    uvicorn.run(create_app(db), host=host, port=port)


@app.command()
def report(
    run_id: int = typer.Argument(..., help="Run id to report."),
    db: Path = typer.Option(Path("runs/alphaforge.sqlite")),
) -> None:
    """Print the markdown report for a run."""
    console.print(generate_markdown_report(ExperimentStore(db), run_id))


@app.command()
def version() -> None:
    from alphaforge import __version__

    console.print(f"alphaforge {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
