"""Fetch a slice of REAL Binance USDT-M futures market data and convert it into
the normalized event schema QuantResearchAgent's loader understands.

We use two free, unauthenticated public dumps from data.binance.vision:
  - bookTicker : best bid/ask updates  -> reconstruct top-of-book ADD/CANCEL
  - aggTrades  : aggregated trades     -> TRADE events (aggressor side)

The daily bookTicker file for a liquid symbol is huge (~200 MB zipped), but we
only need a few hundred thousand events. So we STREAM the zip, inflate its single
deflate member on the fly, and stop after N rows -- the actual download is only a
few MB. Output is a tidy CSV: ts,event,side,price,qty,order_id.

Usage:
    uv run python scripts/fetch_real_data.py --symbol BTCUSDT --date 2024-01-02
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

import httpx

_BASE = "https://data.binance.vision/data/futures/um/daily"
# Real crypto quantities are fractional; the engine uses integer sizes, so scale
# then round. PnL lands in scaled units but Sharpe/PBO/etc. are scale-invariant.
_QTY_SCALE = 1000.0


def _stream_zip_lines(url: str, max_rows: int, timeout: float = 60.0):
    """Yield decoded text lines from a single-member zip, stopping after max_rows.

    Parses the local file header, then incrementally inflates the raw deflate
    stream so we never download more than necessary.
    """
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
        resp.raise_for_status()
        header = b""
        body_inflater: zlib._Decompress | None = None
        method = None
        text_buf = ""
        emitted = 0

        for chunk in resp.iter_bytes():
            if body_inflater is None and method is None:
                header += chunk
                if len(header) < 30:
                    continue
                (sig,) = struct.unpack_from("<I", header, 0)
                if sig != 0x04034B50:
                    raise ValueError("not a zip local file header")
                method = struct.unpack_from("<H", header, 8)[0]
                name_len = struct.unpack_from("<H", header, 26)[0]
                extra_len = struct.unpack_from("<H", header, 28)[0]
                start = 30 + name_len + extra_len
                if len(header) < start:
                    continue
                body = header[start:]
                body_inflater = zlib.decompressobj(-15)  # raw deflate
                chunk = body
            elif body_inflater is None:
                continue

            data = body_inflater.decompress(chunk) if method == 8 else chunk
            if not data:
                continue
            text_buf += data.decode("utf-8", errors="replace")
            while "\n" in text_buf:
                line, text_buf = text_buf.split("\n", 1)
                line = line.strip("\r")
                if not line:
                    continue
                yield line
                emitted += 1
                if emitted >= max_rows:
                    return


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def fetch_book_events(symbol: str, date: str, max_rows: int):
    """Reconstruct top-of-book ADD/CANCEL events from bookTicker updates."""
    url = f"{_BASE}/bookTicker/{symbol}/{symbol}-bookTicker-{date}.zip"
    events = []
    oid = 1
    cur = {"buy": None, "sell": None}  # side -> (order_id, price, qty)
    last = {"buy": (None, None), "sell": (None, None)}
    first = True
    for line in _stream_zip_lines(url, max_rows):
        f = line.split(",")
        if first:
            first = False
            if not _is_number(f[1]):  # header row
                continue
        # columns: update_id,bid_px,bid_qty,ask_px,ask_qty,transaction_time,event_time
        try:
            bid_px, bid_qty = float(f[1]), float(f[2])
            ask_px, ask_qty = float(f[3]), float(f[4])
            ts_ns = int(f[5]) * 1_000_000
        except (IndexError, ValueError):
            continue

        for side, px, qty in (("buy", bid_px, bid_qty), ("sell", ask_px, ask_qty)):
            if (px, qty) == last[side]:
                continue
            last[side] = (px, qty)
            prev = cur[side]
            if prev is not None:
                events.append((ts_ns, "cancel", side, 0.0, 0, prev[0]))
                cur[side] = None
            sized = int(round(qty * _QTY_SCALE))
            if px > 0 and sized > 0:
                events.append((ts_ns, "add", side, px, sized, oid))
                cur[side] = (oid, px, sized)
                oid += 1
    return events


def fetch_trade_events(symbol: str, date: str, max_rows: int):
    url = f"{_BASE}/aggTrades/{symbol}/{symbol}-aggTrades-{date}.zip"
    events = []
    first = True
    for line in _stream_zip_lines(url, max_rows):
        f = line.split(",")
        if first:
            first = False
            if not _is_number(f[1]):
                continue
        # columns: agg_id,price,qty,first_id,last_id,transact_time,is_buyer_maker
        try:
            price = float(f[1])
            qty = float(f[2])
            ts_ns = int(f[5]) * 1_000_000
            is_buyer_maker = str(f[6]).strip().lower() in ("true", "1")
        except (IndexError, ValueError):
            continue
        side = "sell" if is_buyer_maker else "buy"  # aggressor side
        sized = int(round(qty * _QTY_SCALE))
        if sized > 0:
            events.append((ts_ns, "trade", side, price, sized, 0))
    return events


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--date", default="2024-01-02", help="YYYY-MM-DD")
    ap.add_argument("--book-rows", type=int, default=400_000)
    ap.add_argument("--trade-rows", type=int, default=150_000)
    ap.add_argument("--max-events", type=int, default=300_000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    print(f"streaming bookTicker for {args.symbol} {args.date} ...")
    book = fetch_book_events(args.symbol, args.date, args.book_rows)
    print(f"  reconstructed {len(book):,} book events")
    print(f"streaming aggTrades for {args.symbol} {args.date} ...")
    trades = fetch_trade_events(args.symbol, args.date, args.trade_rows)
    print(f"  parsed {len(trades):,} trade events")

    if not book:
        raise SystemExit("no book events parsed")

    # Restrict both streams to their overlapping time window, then merge.
    b_lo, b_hi = book[0][0], book[-1][0]
    t_lo = trades[0][0] if trades else b_lo
    t_hi = trades[-1][0] if trades else b_hi
    lo, hi = max(b_lo, t_lo), min(b_hi, t_hi)
    merged = [e for e in (book + trades) if lo <= e[0] <= hi]
    merged.sort(key=lambda e: e[0])
    merged = merged[: args.max_events]

    out = Path(args.out or f"data/raw/{args.symbol}_{args.date}_real.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write("ts,event,side,price,qty,order_id\n")
        for ts, ev, side, px, qty, oid in merged:
            fh.write(f"{ts},{ev},{side},{px},{qty},{oid}\n")

    span_s = (merged[-1][0] - merged[0][0]) / 1e9 if merged else 0.0
    print(f"wrote {len(merged):,} events covering {span_s:.1f}s -> {out}")


if __name__ == "__main__":
    main()
