"""SQLite experiment store.

Every run, experiment (hypothesis + code + validation metrics), out-of-sample
evaluation, and model-usage record is persisted so results are auditable and
reproducible, and so the dashboard can diff agent versions across runs.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL, seed INTEGER, symbol TEXT,
    model_provider TEXT, model_name TEXT, n_experiments INTEGER,
    dataset_fingerprint TEXT, pbo REAL, n_survivors INTEGER,
    survival_rate REAL, best_baseline_sharpe REAL, config_json TEXT
);
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, experiment_id INTEGER, hypothesis TEXT,
    strategy_name TEXT, strategy_code TEXT, val_sharpe REAL,
    submitted INTEGER, steps INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, experiment_id INTEGER, strategy_name TEXT,
    holdout_sharpe REAL, holdout_return REAL, max_drawdown REAL,
    pvalue REAL, adjusted_pvalue REAL, deflated_sr REAL,
    beats_baselines INTEGER, significant INTEGER, survived INTEGER,
    wf_mean_sharpe REAL, wf_frac_positive REAL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, provider TEXT, model TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER,
    cost REAL, cached INTEGER, latency REAL
);
"""


@dataclass(slots=True)
class RunRow:
    id: int
    created_at: float
    symbol: str
    model_name: str
    n_experiments: int
    pbo: float
    n_survivors: int
    survival_rate: float


class ExperimentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con:
            con.executescript(_SCHEMA)
            con.commit()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def create_run(self, **fields: Any) -> int:
        fields.setdefault("created_at", time.time())
        cols = ", ".join(fields)
        ph = ", ".join("?" for _ in fields)
        with closing(self._connect()) as con:
            cur = con.execute(f"INSERT INTO runs ({cols}) VALUES ({ph})", tuple(fields.values()))
            con.commit()
            return int(cur.lastrowid)

    def update_run(self, run_id: int, **fields: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with closing(self._connect()) as con:
            con.execute(f"UPDATE runs SET {sets} WHERE id = ?", (*fields.values(), run_id))
            con.commit()

    def add_experiment(self, run_id: int, **fields: Any) -> int:
        fields["run_id"] = run_id
        cols = ", ".join(fields)
        ph = ", ".join("?" for _ in fields)
        with closing(self._connect()) as con:
            cur = con.execute(
                f"INSERT INTO experiments ({cols}) VALUES ({ph})", tuple(fields.values())
            )
            con.commit()
            return int(cur.lastrowid)

    def add_evaluation(self, run_id: int, **fields: Any) -> None:
        fields["run_id"] = run_id
        cols = ", ".join(fields)
        ph = ", ".join("?" for _ in fields)
        with closing(self._connect()) as con:
            con.execute(f"INSERT INTO evaluations ({cols}) VALUES ({ph})", tuple(fields.values()))
            con.commit()

    def add_usage(self, run_id: int, **fields: Any) -> None:
        fields["run_id"] = run_id
        cols = ", ".join(fields)
        ph = ", ".join("?" for _ in fields)
        with closing(self._connect()) as con:
            con.execute(f"INSERT INTO usage ({cols}) VALUES ({ph})", tuple(fields.values()))
            con.commit()

    # --- queries -----------------------------------------------------------
    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def run(self, run_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as con:
            row = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            return dict(row) if row else None

    def evaluations_for(self, run_id: int) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT * FROM evaluations WHERE run_id = ? ORDER BY holdout_sharpe DESC",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def leaderboard(self, limit: int = 25) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            rows = con.execute(
                """
                SELECT e.*, r.symbol, r.model_name, r.created_at
                FROM evaluations e JOIN runs r ON e.run_id = r.id
                ORDER BY e.survived DESC, e.holdout_sharpe DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def usage_totals(self, run_id: int) -> dict[str, float]:
        with closing(self._connect()) as con:
            row = con.execute(
                """
                SELECT COALESCE(SUM(prompt_tokens),0) p, COALESCE(SUM(completion_tokens),0) c,
                       COALESCE(SUM(cost),0) cost, COALESCE(SUM(latency),0) latency,
                       COALESCE(SUM(cached),0) cached, COUNT(*) calls
                FROM usage WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            return dict(row) if row else {}
