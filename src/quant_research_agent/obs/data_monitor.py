"""Scan recorded market-data directories for the monitoring dashboard.

Looks under a configurable root (default ``data/raw``) for either:

* a subdirectory of segment parquet files (``fetch-okx-long`` output), or
* loose ``.parquet`` / ``.csv`` files at the root (``fetch-okx`` output).

Each group becomes a "dataset" with file counts, event totals, time span, and
an ``active`` flag based on recent file mtimes (proxy for an ongoing recorder).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import polars as pl

# Default: treat a dataset as "actively recording" if any file was written
# within the last 20 minutes (2x the default 10-minute segment window).
DEFAULT_ACTIVE_WINDOW_S = 20 * 60


@dataclass(slots=True)
class SegmentInfo:
    name: str
    path: str
    size_bytes: int
    mtime: float
    n_events: int
    ts_min: int | None
    ts_max: int | None


@dataclass(slots=True)
class DatasetSummary:
    name: str
    path: str
    kind: str  # "directory" | "file"
    n_files: int
    n_events: int
    size_bytes: int
    latest_mtime: float
    ts_min: int | None
    ts_max: int | None
    active: bool
    segments: list[SegmentInfo]


def _stat_frame(path: Path) -> tuple[int, int | None, int | None]:
    """Return (n_events, ts_min, ts_max) for a parquet/csv file. Best-effort."""
    try:
        if path.suffix == ".parquet":
            schema = pl.scan_parquet(path).collect_schema()
            if "ts" in schema:
                row = (
                    pl.scan_parquet(path)
                    .select(
                        pl.len().alias("n"),
                        pl.col("ts").min().alias("ts_min"),
                        pl.col("ts").max().alias("ts_max"),
                    )
                    .collect()
                    .row(0)
                )
                return (
                    int(row[0]),
                    int(row[1]) if row[1] is not None else None,
                    int(row[2]) if row[2] is not None else None,
                )
            n = pl.scan_parquet(path).select(pl.len()).collect().item()
            return int(n), None, None
        if path.suffix == ".csv":
            df = pl.read_csv(path)
            n = df.height
            if "ts" in df.columns and n:
                return n, int(df["ts"].min()), int(df["ts"].max())
            return n, None, None
    except Exception:
        return 0, None, None
    return 0, None, None


def _segment_info(path: Path) -> SegmentInfo:
    st = path.stat()
    n, ts_min, ts_max = _stat_frame(path)
    return SegmentInfo(
        name=path.name,
        path=str(path.resolve()),
        size_bytes=int(st.st_size),
        mtime=float(st.st_mtime),
        n_events=n,
        ts_min=ts_min,
        ts_max=ts_max,
    )


def _summarize(name: str, path: Path, files: list[Path], active_window_s: float) -> DatasetSummary:
    segments = [_segment_info(f) for f in sorted(files)]
    now = time.time()
    latest = max((s.mtime for s in segments), default=0.0)
    ts_mins = [s.ts_min for s in segments if s.ts_min is not None]
    ts_maxs = [s.ts_max for s in segments if s.ts_max is not None]
    return DatasetSummary(
        name=name,
        path=str(path.resolve()),
        kind="directory" if path.is_dir() else "file",
        n_files=len(segments),
        n_events=sum(s.n_events for s in segments),
        size_bytes=sum(s.size_bytes for s in segments),
        latest_mtime=latest,
        ts_min=min(ts_mins) if ts_mins else None,
        ts_max=max(ts_maxs) if ts_maxs else None,
        active=bool(segments) and (now - latest) <= active_window_s,
        segments=segments,
    )


def list_datasets(
    root: str | Path,
    active_window_s: float = DEFAULT_ACTIVE_WINDOW_S,
) -> list[dict[str, Any]]:
    """Scan ``root`` and return dataset summaries (without per-file detail for list view)."""
    root = Path(root)
    if not root.exists():
        return []

    summaries: list[DatasetSummary] = []

    # Subdirectories with parquet/csv segments
    for child in sorted(root.iterdir()):
        if child.is_dir():
            files = sorted([*child.glob("*.parquet"), *child.glob("*.csv")])
            if files:
                summaries.append(_summarize(child.name, child, files, active_window_s))

    # Loose files at root
    for f in sorted([*root.glob("*.parquet"), *root.glob("*.csv")]):
        summaries.append(_summarize(f.stem, f, [f], active_window_s))

    # List view: omit heavy segment payloads
    out: list[dict[str, Any]] = []
    for s in summaries:
        d = asdict(s)
        d.pop("segments", None)
        out.append(d)
    return out


def get_dataset(
    root: str | Path,
    name: str,
    active_window_s: float = DEFAULT_ACTIVE_WINDOW_S,
) -> dict[str, Any] | None:
    """Return one dataset with full segment list, or None if not found."""
    root = Path(root)
    if not root.exists():
        return None

    candidate_dir = root / name
    if candidate_dir.is_dir():
        files = sorted([*candidate_dir.glob("*.parquet"), *candidate_dir.glob("*.csv")])
        if files:
            return asdict(_summarize(name, candidate_dir, files, active_window_s))

    for f in [*root.glob("*.parquet"), *root.glob("*.csv")]:
        if f.stem == name:
            return asdict(_summarize(f.stem, f, [f], active_window_s))

    return None


def delete_dataset(root: str | Path, name: str) -> bool:
    """Delete a dataset directory or loose file under ``root``. Returns True if removed."""
    import shutil

    root = Path(root).resolve()
    if not root.exists():
        return False

    candidate_dir = (root / name).resolve()
    if candidate_dir.is_dir() and candidate_dir.parent == root:
        shutil.rmtree(candidate_dir)
        return True

    for f in [*root.glob("*.parquet"), *root.glob("*.csv")]:
        if f.stem == name:
            f.unlink()
            return True
    return False


def delete_segment(root: str | Path, dataset: str, filename: str) -> bool:
    """Delete one segment file inside a dataset directory."""
    root = Path(root).resolve()
    path = (root / dataset / filename).resolve()
    if not str(path).startswith(str(root)):
        return False
    if path.is_file() and path.parent.name == dataset:
        path.unlink()
        return True
    return False
