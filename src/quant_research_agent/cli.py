"""QuantResearchAgent command-line interface."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quant_research_agent.config import (
    AgentConfig,
    QuantResearchAgentConfig,
    DataConfig,
    ModelConfig,
    SandboxConfig,
)
from quant_research_agent.obs.store import ExperimentStore
from quant_research_agent.orchestrator import Orchestrator
from quant_research_agent.report import generate_markdown_report, write_report

app = typer.Typer(add_completion=False, help="QuantResearchAgent: autonomous quant-research agent harness.")
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
    db: Path = typer.Option(Path("runs/quant_research_agent.sqlite"), help="Experiment DB path."),
) -> None:
    """Run the autonomous research loop and the out-of-sample evaluation."""
    cfg = QuantResearchAgentConfig(
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


@app.command(name="fetch-okx")
def fetch_okx_cmd(
    out: Path = typer.Argument(..., help="Output file (.parquet or .csv) for the recorded events."),
    inst_id: str = typer.Option("BTC-USDT", help="OKX instrument, e.g. BTC-USDT or BTC-USDT-SWAP."),
    duration: float = typer.Option(60.0, help="Seconds to record the live stream."),
    qty_scale: float = typer.Option(
        1e6, help="Multiplier on fractional sizes before integer rounding (0.001 BTC -> 1000)."
    ),
    max_events: int = typer.Option(None, help="Optional early stop after this many events."),
    channel: str = typer.Option("books", help="Order-book depth channel (books = 400 levels)."),
) -> None:
    """Record live OKX L2 depth + trades into a crypto_l2-compatible file.

    Then run research on it, e.g.::

        qra fetch-okx data/raw/okx_btc.parquet --duration 120
        qra research --data-source crypto_l2 --data-path data/raw/okx_btc.parquet \
            --symbol BTC-USDT --tick-size 0.1
    """
    from quant_research_agent.data.okx import fetch_okx

    console.print(
        f"Recording OKX [bold]{inst_id}[/bold] ({channel}+trades) for {duration:.0f}s -> {out}"
    )
    path = fetch_okx(
        out_path=out,
        inst_id=inst_id,
        duration_s=duration,
        qty_scale=qty_scale,
        max_events=max_events,
        channel=channel,
    )
    import polars as pl

    n = pl.read_parquet(path).height if path.suffix != ".csv" else pl.read_csv(path).height
    console.print(f"Wrote [bold]{n}[/bold] events to [bold]{path}[/bold]")
    console.print(
        f"Run: qra research --data-source crypto_l2 --data-path {path} "
        f"--symbol {inst_id} --tick-size 0.1"
    )


@app.command(name="fetch-okx-long")
def fetch_okx_long_cmd(
    out_dir: Path = typer.Argument(..., help="Directory to write segment files into."),
    inst_id: str = typer.Option("BTC-USDT", help="OKX instrument, e.g. BTC-USDT or BTC-USDT-SWAP."),
    segment_minutes: float = typer.Option(10.0, help="Minutes of data per file."),
    total_minutes: float = typer.Option(
        None, help="Total run length in minutes; omit to run until Ctrl+C."
    ),
    qty_scale: float = typer.Option(
        1e6, help="Multiplier on fractional sizes before integer rounding (0.001 BTC -> 1000)."
    ),
    channel: str = typer.Option("books", help="Order-book depth channel (books = 400 levels)."),
) -> None:
    """Long-run OKX recorder: one file per segment, auto-reconnect, crash-safe.

    Writes ``<inst>_0001.parquet``, ``_0002`` ... Stop anytime with Ctrl+C (the
    partial last segment is still saved). Run research over the whole directory::

        qra fetch-okx-long data/raw/okx_btc --segment-minutes 10
        qra research --data-source crypto_l2 --data-path data/raw/okx_btc \
            --symbol BTC-USDT --tick-size 0.1
    """
    from quant_research_agent.data.okx import record_okx_segmented

    total = f"{total_minutes:.0f} min" if total_minutes else "until Ctrl+C"
    console.print(
        f"Recording OKX [bold]{inst_id}[/bold] -> {out_dir} "
        f"(every {segment_minutes:.0f} min, {total})"
    )

    def _report(path: Path, n: int) -> None:
        console.print(f"  segment [bold]{path.name}[/bold] ({n} events)")

    def _reconnect(attempt: int, exc: Exception) -> None:
        console.print(
            f"  [yellow]connection dropped ({type(exc).__name__}); "
            f"reconnect attempt {attempt}...[/yellow]"
        )

    try:
        paths = record_okx_segmented(
            out_dir=out_dir,
            inst_id=inst_id,
            segment_s=segment_minutes * 60.0,
            total_duration_s=(total_minutes * 60.0 if total_minutes else None),
            qty_scale=qty_scale,
            channel=channel,
            on_segment=_report,
            on_reconnect=_reconnect,
        )
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted; final segment flushed.[/yellow]")
        return
    console.print(f"Wrote [bold]{len(paths)}[/bold] segment files to [bold]{out_dir}[/bold]")
    console.print(
        f"Run: qra research --data-source crypto_l2 --data-path {out_dir} "
        f"--symbol {inst_id} --tick-size 0.1"
    )


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    db: Path = typer.Option(Path("runs/quant_research_agent.sqlite")),
) -> None:
    """Launch the results dashboard."""
    import uvicorn

    from quant_research_agent.obs.dashboard import create_app

    uvicorn.run(create_app(db), host=host, port=port)


@app.command()
def report(
    run_id: int = typer.Argument(..., help="Run id to report."),
    db: Path = typer.Option(Path("runs/quant_research_agent.sqlite")),
) -> None:
    """Print the markdown report for a run."""
    console.print(generate_markdown_report(ExperimentStore(db), run_id))


@app.command()
def version() -> None:
    from quant_research_agent import __version__

    console.print(f"quant_research_agent {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
