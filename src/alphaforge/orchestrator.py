"""Research orchestrator.

Runs N research experiments with bounded concurrency, then performs the single
harness-side out-of-sample evaluation over the whole submitted population. All
artifacts are persisted to the experiment store, and the cross-experiment
journal is updated with holdout verdicts.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from pathlib import Path

from alphaforge.agent.journal import Journal, JournalEntry
from alphaforge.agent.loop import AgentResult, ResearchAgent
from alphaforge.config import AlphaforgeConfig
from alphaforge.data import load_dataset
from alphaforge.eval.protocol import Candidate, EvaluationReport, OutOfSampleEvaluator
from alphaforge.integrity import dataset_fingerprint
from alphaforge.models.cache import ResponseCache
from alphaforge.models.gateway import ModelGateway
from alphaforge.obs.ledger import CostLedger
from alphaforge.obs.store import ExperimentStore
from alphaforge.obs.tracing import span
from alphaforge.tools import default_registry
from alphaforge.tools.base import ToolContext


@dataclass(slots=True)
class RunSummary:
    run_id: int
    report: EvaluationReport
    n_submitted: int
    ledger: dict
    dataset_symbol: str


class Orchestrator:
    def __init__(self, config: AlphaforgeConfig) -> None:
        self.config = config
        self.store = ExperimentStore(config.db_path)
        self.ledger = CostLedger()
        self.cache = ResponseCache(Path(config.run_dir) / "cache")
        self.journal = Journal(max_entries=config.agent.journal_max_entries)

    async def run(self) -> RunSummary:
        cfg = self.config
        dataset = load_dataset(cfg.data, cfg.seed)

        run_id = self.store.create_run(
            seed=cfg.seed,
            symbol=dataset.symbol,
            model_provider=cfg.model.provider,
            model_name=cfg.model.model,
            n_experiments=cfg.n_experiments,
            dataset_fingerprint=dataset_fingerprint(dataset),
            pbo=None,
            n_survivors=0,
            survival_rate=0.0,
            best_baseline_sharpe=0.0,
            config_json=cfg.model_dump_json(),
        )

        def on_usage(provider, model, pt, ct, cost, cached, latency):  # noqa: ANN001
            self.ledger.record(provider, model, pt, ct, cost, cached, latency)
            self.store.add_usage(
                run_id,
                provider=provider,
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                cost=cost,
                cached=int(cached),
                latency=latency,
            )

        gateway = ModelGateway(
            cfg.model,
            cache=self.cache,
            max_concurrency=cfg.max_parallel,
            on_usage=on_usage,
        )

        sandbox = None
        if cfg.use_sandbox:
            from alphaforge.sandbox import build_sandbox

            sandbox = build_sandbox(cfg.sandbox)

        sem = asyncio.Semaphore(cfg.max_parallel)

        async def one_experiment(exp_id: int) -> tuple[int, AgentResult, ToolContext]:
            async with sem:
                workspace = Path(cfg.run_dir) / f"run_{run_id}" / f"exp_{exp_id}"
                workspace.mkdir(parents=True, exist_ok=True)
                ctx = ToolContext(
                    workspace=workspace,
                    dataset=dataset,
                    sim_config=cfg.sim,
                    eval_config=cfg.eval,
                    decision_interval_ns=cfg.data.decision_interval_ns,
                    sandbox=sandbox,
                )
                agent = ResearchAgent(gateway, default_registry(), cfg.agent)
                extra = (
                    f"This is experiment #{exp_id}. Explore a hypothesis distinct from prior "
                    f"experiments."
                )
                try:
                    with span("experiment", experiment_id=exp_id):
                        result = await agent.run(ctx, self.journal.render(), extra_context=extra)
                except Exception as exc:  # noqa: BLE001 - one failed experiment must not kill the run
                    print(f"[experiment {exp_id}] failed: {type(exc).__name__}: {exc}")
                    result = AgentResult(
                        submitted=False,
                        strategy_path=None,
                        steps=0,
                        prompt_tokens=0,
                        completion_tokens=0,
                    )
                return exp_id, result, ctx

        results = await asyncio.gather(
            *(one_experiment(i) for i in range(cfg.n_experiments))
        )

        candidates: list[Candidate] = []
        for exp_id, result, ctx in results:
            val_sharpe = (
                float(result.final_val_metrics.get("sharpe", 0.0))
                if result.final_val_metrics
                else 0.0
            )
            code = ""
            name = f"exp_{exp_id}"
            if result.strategy_path and result.strategy_path.exists():
                code = result.strategy_path.read_text()
                name = result.strategy_path.stem
            hypothesis = result.hypotheses[0] if result.hypotheses else ""
            self.store.add_experiment(
                run_id,
                experiment_id=exp_id,
                hypothesis=hypothesis,
                strategy_name=name,
                strategy_code=code,
                val_sharpe=val_sharpe,
                submitted=int(result.submitted),
                steps=result.steps,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
            if result.submitted and result.strategy_path is not None:
                candidates.append(
                    Candidate(
                        experiment_id=exp_id,
                        name=name,
                        strategy_path=result.strategy_path,
                        val_metrics=result.final_val_metrics,
                        hypothesis=hypothesis,
                    )
                )

        evaluator = OutOfSampleEvaluator(
            dataset, cfg.sim, cfg.eval, cfg.data.decision_interval_ns
        )
        with span("out_of_sample_eval", n_candidates=len(candidates)):
            report = await asyncio.to_thread(evaluator.evaluate, candidates)

        for ev in report.evaluations:
            self.store.add_evaluation(
                run_id,
                experiment_id=ev.candidate.experiment_id,
                strategy_name=ev.candidate.name,
                holdout_sharpe=ev.holdout_metrics.sharpe,
                holdout_return=ev.holdout_metrics.total_return,
                max_drawdown=ev.holdout_metrics.max_drawdown,
                pvalue=ev.pvalue,
                adjusted_pvalue=ev.adjusted_pvalue,
                deflated_sr=ev.deflated_sr,
                beats_baselines=int(ev.beats_baselines),
                significant=int(ev.significant),
                survived=int(ev.survived),
                wf_mean_sharpe=ev.walk_forward.mean_sharpe,
                wf_frac_positive=ev.walk_forward.frac_positive,
            )
            self.journal.add(
                JournalEntry(
                    experiment_id=ev.candidate.experiment_id,
                    hypothesis=ev.candidate.hypothesis,
                    strategy_name=ev.candidate.name,
                    val_sharpe=float((ev.candidate.val_metrics or {}).get("sharpe", 0.0)),
                    holdout_sharpe=ev.holdout_metrics.sharpe,
                    survived=ev.survived,
                )
            )

        self.store.update_run(
            run_id,
            pbo=None if math.isnan(report.pbo) else report.pbo,
            n_survivors=report.n_survivors,
            survival_rate=report.survival_rate,
            best_baseline_sharpe=report.best_baseline_sharpe,
        )

        return RunSummary(
            run_id=run_id,
            report=report,
            n_submitted=len(candidates),
            ledger=self.ledger.summary(),
            dataset_symbol=dataset.symbol,
        )
