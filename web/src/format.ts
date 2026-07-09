export function fmtNum(x: number | null | undefined, digits = 3): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return Number(x).toFixed(digits);
}

export function fmtPct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${(Number(x) * 100).toFixed(digits)}%`;
}

export function fmtTime(ts: number | null | undefined): string {
  if (!ts) return "—";
  // Heuristic: ns timestamps from market data vs unix seconds
  const ms = ts > 1e15 ? ts / 1e6 : ts > 1e12 ? ts : ts * 1000;
  return new Date(ms).toLocaleString();
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function relativeAge(mtime: number): string {
  const sec = Math.max(0, Date.now() / 1000 - mtime);
  if (sec < 60) return `${Math.floor(sec)}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}
