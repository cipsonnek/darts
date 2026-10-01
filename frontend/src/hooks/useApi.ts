import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/** GET a resource; optional polling interval for slowly changing data (not for live frames). */
export function useApi<T>(path: string | null, intervalMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api.get<T>(path);
      if (alive.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    load();
    if (!intervalMs) return () => { alive.current = false; };
    const t = setInterval(load, intervalMs);
    return () => {
      alive.current = false;
      clearInterval(t);
    };
  }, [load, intervalMs]);

  return { data, error, loading, reload: load, setData };
}

/** Wrap an async action with busy/error state. */
export function useAction<A extends unknown[], R>(fn: (...a: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = useCallback(async (...a: A): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn(...a);
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [fn]);
  return { run, busy, error, setError };
}
