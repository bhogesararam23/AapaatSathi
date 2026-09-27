import { useCallback, useEffect, useRef, useState } from "react";

/** Minimal async data hook: fetch on mount, expose `{data, error, loading, reload}`. */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
  options: { enabled?: boolean; intervalMs?: number } = {},
) {
  const { enabled = true, intervalMs } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(enabled);
  const mounted = useRef(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(async () => {
    try {
      setError(null);
      const result = await fnRef.current();
      if (mounted.current) setData(result);
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    void run();
    if (!intervalMs) return;
    const id = window.setInterval(() => void run(), intervalMs);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs, ...deps]);

  return { data, error, loading, reload: run, setData };
}

export interface Coords {
  lat: number;
  lng: number;
  accuracy: number;
}

/**
 * Browser geolocation with a graceful fallback.
 *
 * A hill resident opening this on a phone will usually have GPS; a judge on a
 * desktop in a hotel may have it denied. Neither should see a broken page, so
 * callers get `null` and a reason rather than an exception.
 */
export function useGeolocate() {
  const [coords, setCoords] = useState<Coords | null>(null);
  const [status, setStatus] = useState<"idle" | "asking" | "granted" | "denied" | "unavailable">("idle");

  const locate = useCallback(() => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setStatus("unavailable");
      return;
    }
    setStatus("asking");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({
          lat: +pos.coords.latitude.toFixed(5),
          lng: +pos.coords.longitude.toFixed(5),
          accuracy: Math.round(pos.coords.accuracy),
        });
        setStatus("granted");
      },
      (err) => setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "unavailable"),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60_000 },
    );
  }, []);

  useEffect(() => {
    locate();
  }, [locate]);

  return { coords, status, locate };
}

export function useInterval(callback: () => void, ms: number | null) {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (ms === null) return;
    const id = window.setInterval(() => saved.current(), ms);
    return () => window.clearInterval(id);
  }, [ms]);
}

/** Ticks every second so "4 min ago" labels stay honest without a re-render storm. */
export function useNow(ms = 15_000) {
  const [now, setNow] = useState(() => Date.now());
  useInterval(() => setNow(Date.now()), ms);
  return now;
}

export function useLocalState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (next: T | ((prev: T) => T)) =>
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          localStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          /* private mode / quota — not worth breaking the UI over */
        }
        return resolved;
      }),
    [key],
  );
  return [value, set] as const;
}
