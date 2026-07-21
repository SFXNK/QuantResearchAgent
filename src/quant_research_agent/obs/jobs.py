"""In-process background job runner for the monitor UI.

Long-running actions (OKX capture, research runs) are launched as asyncio tasks
and polled via ``/api/jobs``. Cancel requests set a stop event / cancel the task.
"""

from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

JobKind = Literal["record", "research"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


@dataclass
class Job:
    id: str
    kind: JobKind
    status: JobStatus
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    params: dict[str, Any] = field(default_factory=dict)
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "params": self.params,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    def __init__(self, data_root: Path, db_path: Path, run_dir: Path = Path("runs")) -> None:
        self.data_root = Path(data_root)
        self.db_path = Path(db_path)
        self.run_dir = Path(run_dir)
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs[:limit]]

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status in ("completed", "failed", "cancelled"):
            return job
        job.stop_event.set()
        if job.task and not job.task.done():
            job.task.cancel()
        job.status = "cancelled"
        job.finished_at = time.time()
        return job

    async def start_record(self, params: dict[str, Any]) -> Job:
        job = Job(
            id=str(uuid.uuid4())[:8],
            kind="record",
            status="queued",
            created_at=time.time(),
            params=params,
        )
        self._jobs[job.id] = job
        job.task = asyncio.create_task(self._run_record(job))
        return job

    async def start_research(self, params: dict[str, Any]) -> Job:
        job = Job(
            id=str(uuid.uuid4())[:8],
            kind="research",
            status="queued",
            created_at=time.time(),
            params=params,
        )
        self._jobs[job.id] = job
        job.task = asyncio.create_task(self._run_research(job))
        return job

    async def _run_record(self, job: Job) -> None:
        from quant_research_agent.data.okx import record_okx_segmented_async

        job.status = "running"
        job.started_at = time.time()
        p = job.params
        try:
            mode = p.get("mode", "long")  # "long" | "short"
            inst_id = str(p.get("inst_id", "BTC-USDT"))
            qty_scale = float(p.get("qty_scale", 1e6))
            channel = str(p.get("channel", "books"))
            name = str(p.get("name") or inst_id.replace("-", "_").lower())
            out_dir = self.data_root / name

            if mode == "short":
                duration_s = float(p.get("duration_s", 60))
                segment_s = max(duration_s, 5.0)
                total_duration_s = duration_s
                segment_minutes_note = None
            else:
                segment_minutes = float(p.get("segment_minutes", 10))
                segment_s = segment_minutes * 60.0
                total_minutes = p.get("total_minutes")
                total_duration_s = float(total_minutes) * 60.0 if total_minutes else None
                segment_minutes_note = segment_minutes

            job.progress = {
                "phase": "recording",
                "out_dir": str(out_dir),
                "segments": 0,
                "mode": mode,
                "segment_minutes": segment_minutes_note,
            }

            def on_segment(path: Path, n: int) -> None:
                job.progress["segments"] = int(job.progress.get("segments", 0)) + 1
                job.progress["last_segment"] = path.name
                job.progress["last_events"] = n

            paths = await record_okx_segmented_async(
                out_dir=out_dir,
                inst_id=inst_id,
                segment_s=segment_s,
                total_duration_s=total_duration_s,
                qty_scale=qty_scale,
                channel=channel,
                prefix=name,
                stop_event=job.stop_event,
                on_segment=on_segment,
                on_reconnect=lambda a, e: job.progress.update(
                    {"reconnect": a, "last_error": f"{type(e).__name__}: {e}"}
                ),
            )
            job.result = {
                "dataset": name,
                "paths": [str(x) for x in paths],
                "n_segments": len(paths),
            }

            if job.stop_event.is_set():
                job.status = "cancelled"
            else:
                job.status = "completed"
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.error = "cancelled"
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        finally:
            job.finished_at = time.time()

    async def _run_research(self, job: Job) -> None:
        from quant_research_agent.config import (
            AgentConfig,
            DataConfig,
            ModelConfig,
            QuantResearchAgentConfig,
            SandboxConfig,
        )
        from quant_research_agent.orchestrator import Orchestrator

        job.status = "running"
        job.started_at = time.time()
        p = job.params
        try:
            model = str(p.get("model", "echo"))
            provider = p.get("provider")
            if not provider:
                if model == "echo":
                    provider = "echo"
                elif ":" in model:
                    provider = "ollama"
                elif str(model).startswith("claude"):
                    provider = "anthropic"
                else:
                    provider = "openai"

            data_source = str(p.get("data_source", "synthetic"))
            data_path = p.get("data_path")
            if data_source == "crypto_l2" and data_path:
                # Allow dataset name relative to data_root
                path = Path(str(data_path))
                if not path.is_absolute() and not path.exists():
                    cand = self.data_root / path
                    if cand.exists():
                        path = cand
                data_path = str(path)

            cfg = QuantResearchAgentConfig(
                seed=int(p.get("seed", 1)),
                run_dir=self.run_dir,
                db_path=self.db_path,
                n_experiments=int(p.get("experiments", 8)),
                max_parallel=int(p.get("max_parallel", 4)),
                use_sandbox=bool(p.get("sandbox", False)),
                data=DataConfig(
                    symbol=str(p.get("symbol", "SYNTH")),
                    source=data_source,
                    path=data_path,
                    tick_size=float(p.get("tick_size", 0.01)),
                    n_events=int(p.get("n_events", 200_000)),
                ),
                agent=AgentConfig(),
                model=ModelConfig(
                    provider=str(provider),
                    model=model,
                    base_url=p.get("base_url"),
                    api_key_env=p.get("api_key_env"),
                ),
                sandbox=SandboxConfig(backend="auto" if p.get("sandbox") else "local"),
            )
            job.progress = {"phase": "research", "model": model, "source": data_source}

            if job.stop_event.is_set():
                job.status = "cancelled"
                return

            summary = await Orchestrator(cfg).run()
            if job.stop_event.is_set():
                job.status = "cancelled"
                job.result = {"run_id": summary.run_id}
            else:
                job.status = "completed"
                job.result = {
                    "run_id": summary.run_id,
                    "n_submitted": summary.n_submitted,
                    "n_survivors": summary.report.n_survivors,
                    "survival_rate": summary.report.survival_rate,
                    "pbo": summary.report.pbo,
                    "symbol": summary.dataset_symbol,
                    "cost_usd": summary.ledger.get("cost_usd"),
                }
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.error = "cancelled"
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        finally:
            job.finished_at = time.time()
