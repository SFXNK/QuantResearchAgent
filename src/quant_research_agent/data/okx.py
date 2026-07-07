"""OKX live data recorder.

OKX publishes full incremental order-book and trade data over a public
WebSocket (no API key, no licensing restrictions), which fits this project's
microstructure event model directly. We subscribe to:

* ``books``  - 400-level L2 depth: one snapshot followed by incremental updates.
* ``trades`` - public prints, tagged with the aggressor (taker) side.

The recorder converts that stream into the same tidy schema that
:mod:`quant_research_agent.data.crypto_l2` expects, so the resulting Parquet file
loads straight through ``load_l2`` / ``--data-source crypto_l2``::

    ts | event | side | price | qty | order_id

Mapping notes
-------------
The matching engine in :mod:`quant_research_agent.sim` reconstructs a per-level
FIFO book from ADD/CANCEL/TRADE events keyed by ``order_id``. OKX publishes
*aggregated* L2 depth (size per price level, not per order), so we model each
price level as a single synthetic resting order:

* a brand-new level -> ``ADD`` with a fresh synthetic ``order_id``;
* a level whose size changes -> ``CANCEL`` of the old id, then ``ADD`` of the
  new size with a fresh id (a replace that keeps the aggregate depth correct);
* a level whose size becomes 0 -> ``CANCEL`` of its id.

This reproduces correct aggregate depth at every timestamp. True per-order queue
position would require L3/market-by-order data, which OKX does not expose
publicly; this is the honest limit of aggregated L2.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

import polars as pl
from websockets.asyncio.client import connect

PUBLIC_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
# AWS region endpoint (sometimes more reachable); used as an automatic fallback.
PUBLIC_WS_URL_AWS = "wss://wsaws.okx.com:8443/ws/v5/public"

_SCHEMA = ["ts", "event", "side", "price", "qty", "order_id"]


class _DepthToEvents:
    """Convert OKX ``books`` snapshots/updates into ADD/CANCEL event rows."""

    def __init__(self, qty_scale: float) -> None:
        self._qty_scale = qty_scale
        # (side, price_str) -> synthetic order_id of the resting level
        self._level_id: dict[tuple[str, str], int] = {}
        self._next_id = 1

    def _scaled_qty(self, size: str) -> int:
        return int(round(float(size) * self._qty_scale))

    def _emit_remove(self, rows: list[dict], ts: int, side: str, px: str) -> None:
        oid = self._level_id.pop((side, px), None)
        if oid is not None:
            rows.append(
                {"ts": ts, "event": "cancel", "side": side, "price": float(px), "qty": 0, "order_id": oid}
            )

    def _emit_set(self, rows: list[dict], ts: int, side: str, px: str, size: str) -> None:
        qty = self._scaled_qty(size)
        if qty <= 0:
            # Sub-tick size that rounds away; treat as a level removal.
            self._emit_remove(rows, ts, side, px)
            return
        # Replace: cancel any existing resting level at this price first.
        self._emit_remove(rows, ts, side, px)
        oid = self._next_id
        self._next_id += 1
        self._level_id[(side, px)] = oid
        rows.append(
            {"ts": ts, "event": "add", "side": side, "price": float(px), "qty": qty, "order_id": oid}
        )

    def on_book(self, action: str, data: dict) -> list[dict]:
        rows: list[dict] = []
        ts = int(data["ts"]) * 1_000_000  # ms -> ns
        if action == "snapshot":
            # Snapshot is the new ground truth. Cancel everything we believed was
            # resting first (matters on a reconnect snapshot, where prior levels
            # would otherwise linger as orphan liquidity), then rebuild from it.
            for (side, px), oid in self._level_id.items():
                rows.append(
                    {"ts": ts, "event": "cancel", "side": side, "price": float(px), "qty": 0, "order_id": oid}
                )
            self._level_id.clear()
        for side, key in (("buy", "bids"), ("sell", "asks")):
            for level in data.get(key, []):
                px, size = level[0], level[1]
                if float(size) == 0.0:
                    self._emit_remove(rows, ts, side, px)
                else:
                    self._emit_set(rows, ts, side, px, size)
        return rows


def _trade_rows(data: Iterable[dict], qty_scale: float) -> list[dict]:
    rows: list[dict] = []
    for t in data:
        qty = int(round(float(t["sz"]) * qty_scale))
        if qty <= 0:
            continue
        rows.append(
            {
                "ts": int(t["ts"]) * 1_000_000,
                "event": "trade",
                "side": str(t["side"]),  # aggressor (taker) side
                "price": float(t["px"]),
                "qty": qty,
                "order_id": 0,
            }
        )
    return rows


def _install_quiet_exception_handler() -> None:
    """Silence a benign websockets 16.0 traceback.

    When the TCP connection to OKX is reset *before* the handshake completes,
    ``connection_made`` never runs, so websockets' ``connection_lost`` raises
    ``AttributeError: ... 'recv_messages'`` from an asyncio callback. It is
    cosmetic noise (the originating ``ConnectionResetError`` is already handled
    by our reconnect loop), so we filter just that one case.
    """
    loop = asyncio.get_running_loop()
    prev = loop.get_exception_handler()

    def handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, AttributeError) and "recv_messages" in str(exc):
            return
        if prev is not None:
            prev(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def _handle_message(raw, depth: _DepthToEvents, channel: str, qty_scale: float, rows: list[dict]) -> None:
    """Parse one OKX WS frame and append any resulting event rows to ``rows``."""
    if raw == "pong":
        return
    msg = json.loads(raw)
    if "event" in msg:  # subscribe ack / error
        if msg.get("event") == "error":
            raise RuntimeError(f"OKX subscribe error: {msg}")
        return
    ch = msg.get("arg", {}).get("channel")
    data = msg.get("data", [])
    if ch == channel:
        for d in data:
            rows.extend(depth.on_book(msg.get("action", "update"), d))
    elif ch == "trades":
        rows.extend(_trade_rows(data, qty_scale))


def _subscribe_msg(inst_id: str, channel: str) -> str:
    return json.dumps(
        {
            "op": "subscribe",
            "args": [
                {"channel": channel, "instId": inst_id},
                {"channel": "trades", "instId": inst_id},
            ],
        }
    )


async def _ping(ws) -> None:
    """OKX expects a literal 'ping' text frame to keep the socket alive."""
    try:
        while True:
            await asyncio.sleep(15)
            await ws.send("ping")
    except (asyncio.CancelledError, Exception):
        return


async def record_okx_async(
    inst_id: str = "BTC-USDT",
    duration_s: float = 60.0,
    qty_scale: float = 1e6,
    max_events: int | None = None,
    channel: str = "books",
    url: str = PUBLIC_WS_URL,
) -> list[dict]:
    """Record OKX ``books`` + ``trades`` for ``inst_id`` into normalized event rows.

    Args:
        inst_id: OKX instrument, e.g. ``BTC-USDT`` (spot) or ``BTC-USDT-SWAP``.
        duration_s: How long to record before disconnecting.
        qty_scale: Multiplier applied to (fractional) sizes before integer
            rounding. Crypto sizes are tiny (e.g. 0.001 BTC); the engine uses
            integer quantities, so scale them up. 1e6 turns 0.001 -> 1000.
        max_events: Optional early stop once this many rows are collected.
        channel: Order-book channel (``books`` = 400 levels, snapshot+updates).
        url: WebSocket endpoint (an AWS fallback is alternated on reconnects).

    The recorder is resilient to dropped connections: a reset/timeout mid-stream
    triggers an automatic reconnect (with backoff, rotating endpoints) and keeps
    accumulating until ``duration_s`` elapses or ``max_events`` is reached. Rows
    collected before a drop are preserved. On reconnect the fresh ``books``
    snapshot rebuilds the book cleanly. An exception is raised only if *nothing*
    could be recorded at all.
    """
    _install_quiet_exception_handler()
    depth = _DepthToEvents(qty_scale)
    rows: list[dict] = []
    sub = _subscribe_msg(inst_id, channel)
    deadline = time.monotonic() + duration_s
    endpoints = [url, PUBLIC_WS_URL_AWS] if url == PUBLIC_WS_URL else [url]

    last_err: Exception | None = None
    attempt = 0
    while time.monotonic() < deadline and (max_events is None or len(rows) < max_events):
        endpoint = endpoints[attempt % len(endpoints)]
        try:
            async with connect(
                endpoint, ping_interval=None, max_size=None, open_timeout=15
            ) as ws:
                await ws.send(sub)
                pinger = asyncio.create_task(_ping(ws))
                try:
                    while time.monotonic() < deadline:
                        if max_events is not None and len(rows) >= max_events:
                            break
                        timeout = max(0.0, deadline - time.monotonic())
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        except TimeoutError:
                            break
                        _handle_message(raw, depth, channel, qty_scale, rows)
                finally:
                    pinger.cancel()
                    with contextlib.suppress(Exception):
                        await pinger
        except Exception as exc:  # connection dropped/reset -> reconnect
            last_err = exc
            attempt += 1
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(min(2.0 * attempt, 10.0))
            continue
        else:
            break  # clean exit: deadline reached or max_events hit

    if not rows and last_err is not None:
        raise RuntimeError(
            f"Failed to record from OKX ({url}): {type(last_err).__name__}: {last_err}"
        ) from last_err
    return rows


def rows_to_frame(rows: Sequence[dict]) -> pl.DataFrame:
    if not rows:
        raise ValueError("No events recorded from OKX (empty stream).")
    return pl.DataFrame(rows, schema_overrides={"ts": pl.Int64, "order_id": pl.Int64}).select(_SCHEMA)


def _write_frame(frame: pl.DataFrame, path: Path) -> None:
    if path.suffix == ".csv":
        frame.write_csv(path)
    else:
        frame.write_parquet(path)


async def record_okx_segmented_async(
    out_dir: str | Path,
    inst_id: str = "BTC-USDT",
    segment_s: float = 600.0,
    total_duration_s: float | None = None,
    qty_scale: float = 1e6,
    channel: str = "books",
    prefix: str | None = None,
    suffix: str = ".parquet",
    on_segment=None,
    on_reconnect=None,
) -> list[Path]:
    """Record OKX continuously, flushing one file every ``segment_s`` seconds.

    Designed for long unattended runs: the stream auto-reconnects on drops and a
    new file is written on each wall-clock segment boundary, so a crash or Ctrl+C
    only ever loses the current (sub-``segment_s``) buffer. The partial final
    segment is flushed on exit.

    A single :class:`_DepthToEvents` is shared across segments so ``order_id``s
    stay globally unique and a CANCEL in a later file correctly refers to an ADD
    in an earlier one. Therefore the segments are meant to be loaded *together*
    (point ``--data-path`` at the directory); ``load_l2`` handles that.

    Args:
        out_dir: Directory to write segment files into (created if missing).
        segment_s: Seconds per file (e.g. 600 = 10 minutes).
        total_duration_s: Total run length; ``None`` runs until interrupted.
        prefix: File name prefix (defaults to a slug of ``inst_id``).
        suffix: ``.parquet`` (default) or ``.csv``.
        on_segment: Optional ``callback(path, n_events)`` after each file write.
        on_reconnect: Optional ``callback(attempt, exc)`` on each reconnect.

    Returns the list of written segment paths.
    """
    _install_quiet_exception_handler()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = prefix or inst_id.replace("-", "_").lower()
    depth = _DepthToEvents(qty_scale)
    sub = _subscribe_msg(inst_id, channel)
    endpoints = [PUBLIC_WS_URL, PUBLIC_WS_URL_AWS]

    seg_rows: list[dict] = []
    written: list[Path] = []
    seg_idx = 1

    def flush() -> None:
        nonlocal seg_idx, seg_rows
        if not seg_rows:
            return
        path = out_dir / f"{prefix}_{seg_idx:04d}{suffix}"
        _write_frame(rows_to_frame(seg_rows), path)
        written.append(path)
        if on_segment is not None:
            on_segment(path, len(seg_rows))
        seg_idx += 1
        seg_rows = []

    start = time.monotonic()
    total_deadline = (start + total_duration_s) if total_duration_s is not None else None
    next_flush = start + segment_s
    attempt = 0

    def expired() -> bool:
        return total_deadline is not None and time.monotonic() >= total_deadline

    try:
        while not expired():
            endpoint = endpoints[attempt % len(endpoints)]
            try:
                async with connect(
                    endpoint, ping_interval=None, max_size=None, open_timeout=15
                ) as ws:
                    await ws.send(sub)
                    pinger = asyncio.create_task(_ping(ws))
                    try:
                        while not expired():
                            now = time.monotonic()
                            if now >= next_flush:
                                flush()
                                while next_flush <= now:  # skip missed windows
                                    next_flush += segment_s
                            bound = next_flush
                            if total_deadline is not None:
                                bound = min(bound, total_deadline)
                            try:
                                raw = await asyncio.wait_for(
                                    ws.recv(), timeout=max(0.0, bound - now)
                                )
                            except TimeoutError:
                                continue  # boundary handled at loop top
                            _handle_message(raw, depth, channel, qty_scale, seg_rows)
                    finally:
                        pinger.cancel()
                        with contextlib.suppress(Exception):
                            await pinger
            except Exception as exc:  # connection dropped/reset -> reconnect, keep buffer
                attempt += 1
                if on_reconnect is not None:
                    on_reconnect(attempt, exc)
                if expired():
                    break
                await asyncio.sleep(min(2.0 * attempt, 10.0))
                continue
            else:
                break
    finally:
        flush()  # persist the final partial segment (also on Ctrl+C)
    return written


def record_okx_segmented(
    out_dir: str | Path,
    inst_id: str = "BTC-USDT",
    segment_s: float = 600.0,
    total_duration_s: float | None = None,
    qty_scale: float = 1e6,
    channel: str = "books",
    prefix: str | None = None,
    suffix: str = ".parquet",
    on_segment=None,
    on_reconnect=None,
) -> list[Path]:
    """Blocking wrapper around :func:`record_okx_segmented_async`."""
    return asyncio.run(
        record_okx_segmented_async(
            out_dir=out_dir,
            inst_id=inst_id,
            segment_s=segment_s,
            total_duration_s=total_duration_s,
            qty_scale=qty_scale,
            channel=channel,
            prefix=prefix,
            suffix=suffix,
            on_segment=on_segment,
            on_reconnect=on_reconnect,
        )
    )


def fetch_okx(
    out_path: str | Path,
    inst_id: str = "BTC-USDT",
    duration_s: float = 60.0,
    qty_scale: float = 1e6,
    max_events: int | None = None,
    channel: str = "books",
) -> Path:
    """Record OKX data and write it to a Parquet/CSV file usable by ``load_l2``.

    Returns the output path. Choose the file extension (``.parquet`` or ``.csv``)
    via ``out_path``.
    """
    rows = asyncio.run(
        record_okx_async(
            inst_id=inst_id,
            duration_s=duration_s,
            qty_scale=qty_scale,
            max_events=max_events,
            channel=channel,
        )
    )
    frame = rows_to_frame(rows)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix == ".csv":
        frame.write_csv(out_path)
    else:
        frame.write_parquet(out_path)
    return out_path
