"""Loader for free crypto L2 order-book + trade data.

Crypto venues publish full order-book and trade data with no licensing
restrictions, which avoids the equities-data licensing pain. Public dumps
(e.g. exchange websocket recordings, or Tardis.dev sample files) come in many
shapes, so we normalize to a single tidy schema and then map float prices onto
the integer-tick grid the matching engine expects.

Expected normalized columns (after `normalize_frame`):
    ts      : int64   nanoseconds
    event   : str     one of {"add", "cancel", "trade"}
    side    : str     one of {"buy"/"bid", "sell"/"ask"}
    price   : float
    qty     : float
    order_id: int64   (0 for trades / anonymized snapshots)
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from quant_research_agent.config import DataConfig
from quant_research_agent.types import EventType, MarketEvent, Side

from .dataset import Dataset
from .partition import partition_events

_EVENT_MAP = {"add": EventType.ADD, "cancel": EventType.CANCEL, "trade": EventType.TRADE}
_SIDE_MAP = {
    "buy": Side.BUY,
    "bid": Side.BUY,
    "b": Side.BUY,
    "sell": Side.SELL,
    "ask": Side.SELL,
    "a": Side.SELL,
    "s": Side.SELL,
}

_PRICE_BASE_TICK = 1000  # keep tick indices positive and away from 0


def normalize_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Best-effort normalization of common column aliases to the tidy schema."""
    rename = {}
    lower = {c.lower(): c for c in df.columns}
    for canonical, aliases in {
        "ts": ["ts", "timestamp", "time", "local_timestamp"],
        "event": ["event", "type", "action", "update_type"],
        "side": ["side", "direction"],
        "price": ["price", "px"],
        "qty": ["qty", "amount", "size", "quantity"],
        "order_id": ["order_id", "id", "oid"],
    }.items():
        for a in aliases:
            if a in lower:
                rename[lower[a]] = canonical
                break
    df = df.rename(rename)
    if "order_id" not in df.columns:
        df = df.with_columns(pl.lit(0).alias("order_id"))
    if "event" not in df.columns:
        df = df.with_columns(pl.lit("trade").alias("event"))
    return df.select(["ts", "event", "side", "price", "qty", "order_id"])


def frame_to_events(df: pl.DataFrame, tick_size: float) -> list[MarketEvent]:
    df = normalize_frame(df).sort("ts")
    events: list[MarketEvent] = []
    for row in df.iter_rows(named=True):
        ev = _EVENT_MAP.get(str(row["event"]).lower())
        side = _SIDE_MAP.get(str(row["side"]).lower())
        if ev is None or side is None:
            continue
        price_tick = int(round(float(row["price"]) / tick_size)) + _PRICE_BASE_TICK
        qty = int(round(float(row["qty"])))
        if qty <= 0 and ev is not EventType.CANCEL:
            continue
        events.append(
            MarketEvent(int(row["ts"]), ev, side, price_tick, max(qty, 0), int(row["order_id"]))
        )
    return events


def load_l2(path: str | Path, cfg: DataConfig, tick_size: float) -> Dataset:
    """Load L2+trade data into a partitioned `Dataset`.

    ``path`` may be a single ``.parquet``/``.csv`` file, a glob pattern, or a
    directory of segment files (e.g. the output of ``record_okx_segmented``); in
    the directory/glob case all matching parquet files are concatenated in name
    order before being sorted by timestamp.
    """
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.parquet"))
        if not files:
            raise ValueError(f"No .parquet segment files found in directory {path}")
        df = pl.concat([pl.read_parquet(f) for f in files], how="vertical")
    elif any(ch in str(path) for ch in "*?[") and path.suffix == ".parquet":
        df = pl.read_parquet(str(path))
    elif path.suffix == ".parquet":
        df = pl.read_parquet(path)
    else:
        df = pl.read_csv(path)
    events = frame_to_events(df, tick_size)
    if not events:
        raise ValueError(f"No usable events parsed from {path}")
    return partition_events(events, cfg, cfg.symbol)
