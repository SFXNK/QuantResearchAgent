"""FastAPI monitoring API + optional SPA static mount.

JSON endpoints power the React dashboard (read + write actions). When
``web_dir`` points at a built ``web/dist``, the SPA is served for non-API routes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .data_monitor import delete_dataset, delete_segment, get_dataset, list_datasets
from .jobs import JobManager
from .store import ExperimentStore


class RecordRequest(BaseModel):
    inst_id: str = "BTC-USDT"
    name: str | None = None
    mode: str = "long"  # long | short
    segment_minutes: float = 10.0
    total_minutes: float | None = None
    duration_s: float = 60.0
    qty_scale: float = 1e6
    channel: str = "books"


class ResearchRequest(BaseModel):
    experiments: int = 8
    model: str = "echo"
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    seed: int = 1
    max_parallel: int = 4
    n_events: int = 200_000
    symbol: str = "SYNTH"
    data_source: str = "synthetic"  # synthetic | crypto_l2
    data_path: str | None = None
    tick_size: float = 0.01
    sandbox: bool = False


class SurvivedPatch(BaseModel):
    survived: bool


def create_app(
    db_path: str | Path,
    data_root: str | Path = "data/raw",
    web_dir: str | Path | None = None,
    run_dir: str | Path = "runs",
) -> FastAPI:
    store = ExperimentStore(db_path)
    data_root = Path(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    web_path = Path(web_dir) if web_dir else None
    jobs = JobManager(data_root=data_root, db_path=Path(db_path), run_dir=Path(run_dir))

    app = FastAPI(title="QuantResearchAgent Monitor", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:8010",
            "http://127.0.0.1:8010",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- read ---------------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "db": str(Path(db_path).resolve()),
            "data_root": str(data_root.resolve()),
        }

    @app.get("/api/overview")
    def overview() -> dict:
        counts = store.overview_counts()
        datasets = list_datasets(data_root)
        active = sum(1 for d in datasets if d.get("active"))
        return {
            **counts,
            "datasets": len(datasets),
            "active_datasets": active,
            "recent_runs": store.list_runs(limit=8),
            "top_survivors": store.survivors(limit=8),
            "jobs": jobs.list_jobs(limit=10),
        }

    @app.get("/api/runs")
    def api_runs(limit: int = 50) -> list[dict]:
        return store.list_runs(limit=limit)

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: int) -> dict:
        run = store.run(run_id)
        if run is None:
            raise HTTPException(404, f"run {run_id} not found")
        return {
            "run": run,
            "evaluations": store.evaluations_for(run_id),
            "usage": store.usage_totals(run_id),
        }

    @app.get("/api/runs/{run_id}/experiments")
    def api_experiments(run_id: int) -> list[dict]:
        if store.run(run_id) is None:
            raise HTTPException(404, f"run {run_id} not found")
        return store.experiments_for(run_id)

    @app.delete("/api/runs/{run_id}")
    def api_delete_run(run_id: int) -> dict:
        if not store.delete_run(run_id):
            raise HTTPException(404, f"run {run_id} not found")
        return {"ok": True, "deleted": run_id}

    @app.get("/api/factors")
    def api_factors(limit: int = 100) -> list[dict]:
        return store.survivors(limit=limit)

    @app.get("/api/factors/{eval_id}")
    def api_factor(eval_id: int) -> dict:
        row = store.evaluation(eval_id)
        if row is None:
            raise HTTPException(404, f"evaluation {eval_id} not found")
        return row

    @app.patch("/api/factors/{eval_id}")
    def api_patch_factor(eval_id: int, body: SurvivedPatch) -> dict:
        row = store.set_survived(eval_id, body.survived)
        if row is None:
            raise HTTPException(404, f"evaluation {eval_id} not found")
        return row

    @app.delete("/api/factors/{eval_id}")
    def api_delete_factor(eval_id: int) -> dict:
        if not store.delete_evaluation(eval_id):
            raise HTTPException(404, f"evaluation {eval_id} not found")
        return {"ok": True, "deleted": eval_id}

    @app.get("/api/leaderboard")
    def api_leaderboard(limit: int = 25) -> list[dict]:
        return store.leaderboard(limit=limit)

    @app.get("/api/data/datasets")
    def api_datasets() -> list[dict]:
        return list_datasets(data_root)

    @app.get("/api/data/datasets/{name}")
    def api_dataset(name: str) -> dict:
        ds = get_dataset(data_root, name)
        if ds is None:
            raise HTTPException(404, f"dataset {name!r} not found under {data_root}")
        return ds

    @app.delete("/api/data/datasets/{name}")
    def api_delete_dataset(name: str) -> dict:
        if not delete_dataset(data_root, name):
            raise HTTPException(404, f"dataset {name!r} not found")
        return {"ok": True, "deleted": name}

    @app.delete("/api/data/datasets/{name}/segments/{filename}")
    def api_delete_segment(name: str, filename: str) -> dict:
        if not delete_segment(data_root, name, filename):
            raise HTTPException(404, f"segment {filename!r} not found in {name!r}")
        return {"ok": True, "deleted": filename}

    # --- jobs / actions -----------------------------------------------------
    @app.get("/api/jobs")
    def api_jobs(limit: int = 50) -> list[dict]:
        return jobs.list_jobs(limit=limit)

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str) -> dict:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"job {job_id} not found")
        return job.to_dict()

    @app.post("/api/jobs/{job_id}/cancel")
    async def api_cancel_job(job_id: str) -> dict:
        try:
            job = await jobs.cancel(job_id)
        except KeyError:
            raise HTTPException(404, f"job {job_id} not found") from None
        return job.to_dict()

    @app.post("/api/actions/record")
    async def api_start_record(body: RecordRequest) -> dict:
        if body.mode not in ("long", "short"):
            raise HTTPException(400, "mode must be 'long' or 'short'")
        name = body.name or body.inst_id.replace("-", "_").lower()
        # refuse to clobber an existing dataset unless name is unique-ish; allow append into dir
        job = await jobs.start_record(
            {
                "inst_id": body.inst_id,
                "name": name,
                "mode": body.mode,
                "segment_minutes": body.segment_minutes,
                "total_minutes": body.total_minutes,
                "duration_s": body.duration_s,
                "qty_scale": body.qty_scale,
                "channel": body.channel,
            }
        )
        return job.to_dict()

    @app.post("/api/actions/research")
    async def api_start_research(body: ResearchRequest) -> dict:
        if body.data_source not in ("synthetic", "crypto_l2"):
            raise HTTPException(400, "data_source must be synthetic|crypto_l2")
        if body.data_source == "crypto_l2" and not body.data_path:
            raise HTTPException(400, "crypto_l2 requires data_path (dataset name or path)")
        job = await jobs.start_research(body.model_dump())
        return job.to_dict()

    # Serve SPA when a built dist exists
    if web_path is not None and web_path.is_dir() and (web_path / "index.html").exists():
        assets = web_path / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:  # noqa: ARG001
            if full_path.startswith("api/"):
                raise HTTPException(404)
            candidate = web_path / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web_path / "index.html")

    return app
