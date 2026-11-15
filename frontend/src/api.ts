import { useCallback, useEffect, useRef, useState } from "react";

export type Json = Record<string, any>;

export async function get<T = Json>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export async function post<T = Json>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Getrich-Action": "1" }, body: JSON.stringify(body ?? {}) });
  const text = await r.text();
  if (!r.ok) {
    let msg = text;
    try { msg = JSON.parse(text).detail ?? text; } catch { /* keep text */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return JSON.parse(text);
}

/** Fetch a path now and every `every` ms (0 = once). Keeps the last good value while a refresh is in flight or fails. */
export function useApi<T = Json>(path: string | null, every = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try { const v = await get<T>(path); if (alive.current) { setData(v); setError(null); } }
    catch (e) { if (alive.current) setError(String((e as Error).message)); }
    finally { if (alive.current) setLoading(false); }
  }, [path]);
  useEffect(() => {
    alive.current = true;
    setData(null);
    load();
    const t = every > 0 ? setInterval(load, every) : undefined;
    return () => { alive.current = false; if (t) clearInterval(t); };
  }, [load, every]);
  return { data, error, loading, reload: load };
}
