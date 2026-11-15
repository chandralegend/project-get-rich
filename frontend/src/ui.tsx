import { ReactNode, useState } from "react";

export const fmt = {
  usd: (x: number | null | undefined, d = 2) => (x == null ? "–" : x.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: d, maximumFractionDigits: d })),
  pct: (x: number | null | undefined, d = 1, sign = false) => (x == null ? "–" : `${sign && x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%`),
  num: (x: number | null | undefined, d = 2) => (x == null ? "–" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })),
  price: (x: number | null | undefined) => (x == null ? "–" : x >= 1000 ? x.toLocaleString("en-US", { maximumFractionDigits: 2 }) : x >= 10 ? x.toFixed(3) : x >= 0.1 ? x.toFixed(4) : x.toPrecision(4)),
  ago: (iso: string | null | undefined) => {
    if (!iso) return "never";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 90) return `${Math.max(0, Math.round(s))}s ago`;
    if (s < 5400) return `${Math.round(s / 60)}m ago`;
    if (s < 172800) return `${(s / 3600).toFixed(1)}h ago`;
    return `${(s / 86400).toFixed(1)}d ago`;
  },
  time: (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "–"),
};

export const tone = (x: number | null | undefined) => (x == null || x === 0 ? "" : x > 0 ? "up" : "dn");

export function Card({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {title != null && <h3>{title}{right != null && <span className="r">{right}</span>}</h3>}
      {children}
    </section>
  );
}

export function Kpi({ label, value, sub, cls = "" }: { label: string; value: ReactNode; sub?: ReactNode; cls?: string }) {
  return <div className="kpi"><div className="l">{label}</div><div className={`v num ${cls}`}>{value}</div>{sub != null && <div className="s">{sub}</div>}</div>;
}

export function Pill({ children, tone: t = "" }: { children: ReactNode; tone?: "" | "up" | "dn" | "warn" | "ac" }) {
  return <span className={`pill ${t}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }

export function Loading({ error }: { error?: string | null }) {
  return <div className="empty">{error ? <span className="dn">Could not load: {error}</span> : "Loading…"}</div>;
}

export function Confirm({ title, body, confirm, danger, onYes, onNo }: { title: string; body: ReactNode; confirm: string; danger?: boolean; onYes: () => void; onNo: () => void }) {
  return (
    <div className="modal" onClick={onNo}>
      <div onClick={(e) => e.stopPropagation()}>
        <b style={{ fontSize: 15 }}>{title}</b>
        <div className="note" style={{ fontSize: 13 }}>{body}</div>
        <div className="row"><span className="sp" /><button className="btn" onClick={onNo}>Cancel</button><button className={`btn ${danger ? "danger" : "primary"}`} onClick={onYes}>{confirm}</button></div>
      </div>
    </div>
  );
}

/** An action button that shows its own progress and error, so no click ever fails silently. */
export function ActionButton({ label, run, className = "btn", disabled, onDone, title }: { label: string; run: () => Promise<unknown>; className?: string; disabled?: boolean; onDone?: (r: any) => void; title?: string }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <span className="row" style={{ gap: 6 }}>
      <button className={className} disabled={disabled || busy} title={title} onClick={async () => { setBusy(true); setErr(null); try { const r = await run(); onDone?.(r); } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); } }}>{busy ? "…" : label}</button>
      {err && <span className="dn" style={{ fontSize: 12 }}>{err}</span>}
    </span>
  );
}

export function Sparkline({ values, height = 120, fill = true }: { values: number[]; height?: number; fill?: boolean }) {
  if (values.length < 2) return <Empty>Not enough history yet.</Empty>;
  const w = 600, pad = 4;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [pad + (i / (values.length - 1)) * (w - 2 * pad), pad + (1 - (v - lo) / span) * (height - 2 * pad)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  const color = up ? "var(--up)" : "var(--dn)";
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" role="img" aria-label="equity curve">
      {fill && <path d={`${d} L${pts[pts.length - 1][0]} ${height} L${pts[0][0]} ${height} Z`} fill={color} opacity="0.08" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function ClassPill({ c }: { c: string }) {
  return <Pill tone={c === "crypto" ? "ac" : c === "fx" ? "warn" : ""}>{c}</Pill>;
}

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return <div className="scroll"><table><thead><tr>{head}</tr></thead><tbody>{children}</tbody></table></div>;
}
