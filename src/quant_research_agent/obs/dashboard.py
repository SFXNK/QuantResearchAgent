"""FastAPI monitoring API + optional SPA static mount.

JSON endpoints power the React dashboard. When ``web_dir`` points at a built
``web/dist``, the SPA is served for non-API routes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .data_monitor import get_dataset, list_datasets
from .store import ExperimentStore


def create_app(
    db_path: str | Path,
    data_root: str | Path = "data/raw",
    web_dir: str | Path | None = None,
) -> FastAPI:
    store = ExperimentStore(db_path)
    data_root = Path(data_root)
    web_path = Path(web_dir) if web_dir else None

    app = FastAPI(title="QuantResearchAgent Monitor", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "db": str(Path(db_path).resolve()), "data_root": str(data_root.resolve())}

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

    @app.get("/api/factors")
    def api_factors(limit: int = 100) -> list[dict]:
        return store.survivors(limit=limit)

    @app.get("/api/factors/{eval_id}")
    def api_factor(eval_id: int) -> dict:
        row = store.survivor(eval_id)
        if row is None:
            raise HTTPException(404, f"survivor evaluation {eval_id} not found")
        return row

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

    # Serve SPA when a built dist exists
    if web_path is not None and web_path.is_dir() and (web_path / "index.html").exists():
        assets = web_path / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:  # noqa: ARG001
            # Never shadow API
            if full_path.startswith("api/"):
                raise HTTPException(404)
            candidate = web_path / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web_path / "index.html")

    return app
