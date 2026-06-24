import httpx

urls = [
    "https://data.binance.vision/data/futures/um/daily/bookTicker/BTCUSDT/BTCUSDT-bookTicker-2024-01-02.zip",
    "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-01-02.zip",
]
for u in urls:
    try:
        r = httpx.head(u, timeout=20, follow_redirects=True)
        size = int(r.headers.get("content-length", 0)) / 1e6
        print("OK", r.status_code, f"{size:.1f} MB", u)
    except Exception as e:
        print("ERR", type(e).__name__, str(e)[:200])
