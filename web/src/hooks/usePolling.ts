import { useCallback, useEffect, useRef, useState } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs = 4000,
  enabled = true,
): { data: T | null; error: string | null; loading: boolean; refresh: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(() => {
    let cancelled = false;
    fetcherRef
      .current()
      .then((v) => {
        if (!cancelled) {
          setData(v);
          setError(null);
          setLoading(false);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const cancel = refresh();
    const id = window.setInterval(() => {
      refresh();
    }, intervalMs);
    return () => {
      cancel();
      window.clearInterval(id);
    };
  }, [refresh, intervalMs, enabled]);

  return { data, error, loading, refresh };
}
