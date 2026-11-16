import { useEffect, useRef, useState } from "react";
import { createChart, LineStyle, SeriesMarker, Time, UTCTimestamp } from "lightweight-charts";
import { useApi, Json } from "./api";
import { Loading, fmt } from "./ui";

export const cssVar = (name: string, fallback = "") => (typeof document === "undefined" ? fallback : getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback);

export type Zone = "buy" | "wait" | "avoid" | "no_read";
export const ZONE_LABEL: Record<Zone, string> = { buy: "BUY ZONE", wait: "WAIT", avoid: "AVOID / SELL", no_read: "NO READ" };
export const zoneColor = (z: Zone) => (z === "buy" ? "var(--up)" : z === "avoid" ? "var(--dn)" : z === "wait" ? "var(--warn)" : "var(--dim)");

/** A half-circle meter: left is avoid / sell, middle is wait, right is buy. The needle shows how much our indicators agree. It is agreement, not a forecast. */
export function Gauge({ score, zone, size = "lg", buy = 0.35, avoid = -0.35 }: { score: number | null; zone: Zone; size?: "lg" | "sm"; buy?: number; avoid?: number }) {
  const cx = 100, cy = 100, r = 78;
  const pt = (s: number, rad = r) => { const a = Math.PI * (1 - (s + 1) / 2); return [cx + rad * Math.cos(a), cy - rad * Math.sin(a)] as const; };
  const arc = (s0: number, s1: number) => { const [x0, y0] = pt(s0), [x1, y1] = pt(s1); return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`; };
  const seg = (z: Zone, a: number, b: number, color: string) => <path d={arc(a, b)} stroke={color} strokeWidth={size === "lg" ? 16 : 18} fill="none" strokeLinecap="butt" opacity={zone === z ? 1 : 0.28} />;
  const [nx, ny] = score == null ? [cx, cy] : pt(Math.max(-1, Math.min(1, score)), r - 14);
  const w = size === "lg" ? 250 : 112;
  return (
    <div className={`gauge ${size}`} style={{ width: w }}>
      <svg viewBox="0 0 200 122" width="100%" role="img" aria-label={`${ZONE_LABEL[zone]}${score == null ? "" : `, agreement ${score.toFixed(2)}`}`}>
        {score == null ? <path d={arc(-1, 1)} stroke="var(--line2)" strokeWidth={16} fill="none" /> : <>{seg("avoid", -1, avoid, "var(--dn)")}{seg("wait", avoid, buy, "var(--warn)")}{seg("buy", buy, 1, "var(--up)")}</>}
        {score != null && <><line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--tx)" strokeWidth={size === "lg" ? 3.5 : 5} strokeLinecap="round" /><circle cx={cx} cy={cy} r={size === "lg" ? 7 : 9} fill="var(--tx)" /></>}
        {size === "lg" && <><text x={14} y={118} fontSize="11" fill="var(--dn)">SELL</text><text x={100} y={16} fontSize="11" fill="var(--warn)" textAnchor="middle">WAIT</text><text x={186} y={118} fontSize="11" fill="var(--up)" textAnchor="end">BUY</text></>}
      </svg>
      <div className="gauge-label" style={{ color: zoneColor(zone) }}>{ZONE_LABEL[zone]}</div>
    </div>
  );
}

const PROOF_TEXT: Record<string, string> = { none: "unproven", weak: "weak evidence" };

/** One row per indicator: a bar to the left (bearish) or right (bullish) of the centre line, and what our own tests found about it. */
export function Votes({ votes }: { votes: Json[] }) {
  return (
    <div className="votes">
      {votes.map((v) => (
        <div className="vote" key={v.id} title={v.proof_note}>
          <div className="vl"><div>{v.label}</div><div className="note">{v.detail}</div></div>
          <div className="vbar">
            <i className="axis" />
            {v.value == null ? <span className="note vnone">no opinion</span> : v.value >= 0
              ? <b className="pos" style={{ width: `${Math.abs(v.value) * 50}%` }} />
              : <b className="neg" style={{ width: `${Math.abs(v.value) * 50}%` }} />}
          </div>
          <span className={`proof ${v.proof}`}>{PROOF_TEXT[v.proof] ?? v.proof}</span>
        </div>
      ))}
    </div>
  );
}

export const MEANING: Record<string, { label: string; color: string }> = {
  buy_candidate: { label: "reconsider a buy", color: "var(--up)" },
  stay_out: { label: "stay out", color: "var(--warn)" },
  exit_or_avoid: { label: "exit / avoid", color: "var(--dn)" },
  trend_change: { label: "trend change", color: "var(--ac)" },
};
const BASIS: Record<string, string> = { daily_close: "daily close", hourly_close: "hourly close", touch: "touch" };

/** Distance from the current price to a trigger, and whether it is already met (a close-based trigger still needs the bar to close). */
export function triggerState(t: Json, price: number | null | undefined) {
  if (!price) return { dist: null as number | null, met: false };
  const dist = t.level / price - 1;
  return { dist, met: t.direction === "above" ? price >= t.level : price <= t.level };
}

export function Triggers({ triggers, prices, only }: { triggers: Json[]; prices: Record<string, number>; only?: string }) {
  const list = triggers.filter((t) => !only || t.instrument === only);
  if (list.length === 0) return <div className="note">No triggers in the latest plan{only ? ` for ${only}` : ""}. Run the trader to get them.</div>;
  return (
    <div className="triggers">
      {list.map((t, i) => {
        const { dist, met } = triggerState(t, prices[t.instrument]);
        const m = MEANING[t.meaning] ?? { label: t.meaning, color: "var(--mu)" };
        const near = dist == null ? 0 : Math.max(0, Math.min(1, 1 - Math.abs(dist) / 0.1));
        return (
          <div className="trig" key={i}>
            <div className="row" style={{ gap: 6 }}>
              {!only && <b>{t.instrument.replace("USDT", "")}</b>}
              <span className="num">{t.direction === "above" ? "↑ above" : "↓ below"} {fmt.price(t.level)}</span>
              <span className="note">{BASIS[t.basis] ?? t.basis}</span>
              <span className="sp" />
              <span className="tpill" style={{ color: m.color, borderColor: m.color }}>{m.label}</span>
            </div>
            <div className="tbar"><i style={{ width: `${met ? 100 : near * 100}%`, background: met ? m.color : "var(--line2)" }} /><u style={{ background: m.color }} /></div>
            <div className="note">{t.note} · {met ? <b style={{ color: m.color }}>met now{t.basis !== "touch" ? ", needs the close to confirm" : ""}</b> : dist == null ? "no price" : <>price needs <b className="num">{fmt.pct(Math.abs(dist), 1)}</b> {t.direction === "above" ? "higher" : "lower"}</>}</div>
          </div>
        );
      })}
    </div>
  );
}

type Layer = "ema" | "levels" | "fan" | "signals" | "triggers" | "calls";
const LAYER_LABEL: Record<Layer, string> = { ema: "EMAs", levels: "Levels", fan: "Forecast fan", signals: "Trend signals", triggers: "Triggers", calls: "Our calls" };

/** Candles with our signals drawn on them: EMAs, the trend rule's flips, key levels, the forecast fan (BTC and ETH), the trader's triggers and past calls. */
export function InstrumentChart({ symbol, triggers = [], height = 400 }: { symbol: string; triggers?: Json[]; height?: number }) {
  const [tf, setTf] = useState<"1d" | "1h">("1d");
  const [layers, setLayers] = useState<Record<Layer, boolean>>({ ema: true, levels: true, fan: true, signals: true, triggers: true, calls: true });
  const data = useApi(`/api/chart/${symbol}?tf=${tf}&limit=${tf === "1d" ? 200 : 300}`, 60000);
  const el = useRef<HTMLDivElement>(null);
  const d = data.data;
  const trigKey = JSON.stringify(triggers.filter((t) => t.instrument === symbol).map((t) => [t.direction, t.level, t.meaning]));

  useEffect(() => {
    if (!el.current || !d || d.symbol !== symbol || d.timeframe !== tf) return;
    const up = cssVar("--up", "#3ddc97"), dn = cssVar("--dn", "#ff6b6b"), ac = cssVar("--ac", "#6ea8ff"), warn = cssVar("--warn", "#f6c177"), mu = cssVar("--mu", "#8b929c"), line = cssVar("--line", "#1c222a");
    const chart = createChart(el.current, {
      height, autoSize: true, layout: { background: { color: "transparent" }, textColor: mu }, grid: { vertLines: { color: line }, horzLines: { color: line } },
      rightPriceScale: { borderColor: cssVar("--line2", "#2a323c") }, timeScale: { borderColor: cssVar("--line2", "#2a323c"), timeVisible: tf === "1h" }, crosshair: { mode: 0 },
    });
    const candles = chart.addCandlestickSeries({ upColor: up, downColor: dn, borderVisible: false, wickUpColor: up, wickDownColor: dn });
    const fanOn = layers.fan && !!d.fan && tf === "1d";
    const horizon = fanOn ? Math.max(...d.fan.points.map((p: Json) => p.h)) : 0;
    const origin: number = fanOn ? d.fan.origin : 0;
    const future = Array.from({ length: horizon }, (_, k) => ({ time: (origin + (k + 1) * 86400) as UTCTimestamp }));      // one empty slot per future day, so the fan has the right width
    candles.setData([...d.bars.map((b: Json) => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })), ...future] as any);
    const times: number[] = d.bars.map((b: Json) => b.t);
    const snap = (t: number) => { let lo = 0, hi = times.length - 1, ans = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (times[m] <= t) { ans = m; lo = m + 1; } else hi = m - 1; } return ans < 0 ? null : times[ans]; };

    if (layers.ema) d.ema.forEach((e: Json, i: number) => chart.addLineSeries({ color: i === 0 ? ac : warn, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: e.name })
      .setData(e.points.map(([t, v]: number[]) => ({ time: t as UTCTimestamp, value: v }))));
    if (layers.levels) d.levels.forEach((l: Json) => candles.createPriceLine({ price: l.price, color: mu, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: l.name }));
    if (layers.triggers) triggers.filter((t) => t.instrument === symbol).forEach((t) => {
      const m = MEANING[t.meaning]; candles.createPriceLine({ price: t.level, color: m ? m.color.replace(/var\((--[a-z]+)\)/, (_s: string, v: string) => cssVar(v, mu)) : mu, lineWidth: 2, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: `${t.direction === "above" ? "↑" : "↓"} ${m?.label ?? t.meaning}` });
    });
    if (fanOn) {
      const f = d.fan;
      const knots = (k: string): [number, number][] => [[0, f.base], ...f.points.map((p: Json): [number, number] => [p.h, p[k]])];
      const pts = (k: string) => {                      // straight lines between the forecast horizons, one point per day
        const ks = knots(k);
        return Array.from({ length: horizon + 1 }, (_, day) => {
          let j = 1; while (j < ks.length - 1 && ks[j][0] < day) j++;
          const [d0, v0] = ks[j - 1], [d1, v1] = ks[j];
          return { time: (origin + day * 86400) as UTCTimestamp, value: v0 + ((v1 - v0) * (day - d0)) / (d1 - d0) };
        });
      };
      const mk = (k: string, color: string, style: LineStyle, w: 1 | 2) => chart.addLineSeries({ color, lineWidth: w, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      mk("p90", up, LineStyle.Dashed, 1).setData(pts("p90"));
      mk("p10", dn, LineStyle.Dashed, 1).setData(pts("p10"));
      const mid = mk("p50", ac, LineStyle.Solid, 2);
      mid.setData(pts("p50"));
      mid.setMarkers(f.points.map((p: Json) => ({ time: p.t as UTCTimestamp, position: "aboveBar", color: ac, shape: "circle", text: `+${p.h}d ${(p.p50 / f.base - 1 >= 0 ? "+" : "")}${((p.p50 / f.base - 1) * 100).toFixed(1)}%` } as SeriesMarker<Time>)));
    }
    const marks: SeriesMarker<Time>[] = [];
    if (layers.signals) d.trend_flips.forEach((s: Json) => { const t = snap(s.t); if (t != null) marks.push({ time: t as UTCTimestamp, position: s.kind === "trend_on" ? "belowBar" : "aboveBar", color: s.kind === "trend_on" ? up : dn, shape: s.kind === "trend_on" ? "arrowUp" : "arrowDown", text: s.kind === "trend_on" ? "trend on" : "trend off" }); });
    if (layers.calls) d.decisions.forEach((c: Json) => { const t = snap(c.t); if (t != null) marks.push({ time: t as UTCTimestamp, position: "inBar", color: c.action === "open_long" ? up : c.action === "wait" ? mu : warn, shape: "circle", text: c.action === "open_long" ? "buy idea" : c.action === "wait" ? "" : c.action.replace("_", " ") }); });
    marks.sort((a, b) => (a.time as number) - (b.time as number));
    if (marks.length) candles.setMarkers(marks);
    const n = d.bars.length, show = tf === "1d" ? 70 : 168;
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - show), to: n - 1 + (horizon || 3) + 2 });
    return () => chart.remove();
  }, [d, layers, trigKey, symbol, tf, height]);

  return (
    <div>
      <div className="row" style={{ marginBottom: 8, flexWrap: "wrap" }}>
        {(["1d", "1h"] as const).map((t) => <button key={t} className={`chip ${tf === t ? "on" : ""}`} onClick={() => setTf(t)}>{t === "1d" ? "Daily" : "Hourly"}</button>)}
        <span className="sp" />
        {(Object.keys(LAYER_LABEL) as Layer[]).filter((l) => l !== "fan" || (tf === "1d" && d?.fan)).map((l) => <button key={l} className={`chip ${layers[l] ? "on" : ""}`} onClick={() => setLayers((x) => ({ ...x, [l]: !x[l] }))}>{LAYER_LABEL[l]}</button>)}
      </div>
      {!d ? <Loading error={data.error} /> : <div ref={el} style={{ minHeight: height }} />}
      {d && (
        <div className="note legend">
          {layers.ema && d.ema.map((e: Json, i: number) => <span key={e.name}><i style={{ background: i === 0 ? "var(--ac)" : "var(--warn)" }} />{e.name}</span>)}
          {layers.fan && d.fan && <span><i style={{ background: "var(--ac)" }} />forecast median, <i style={{ background: "var(--up)" }} />90th and <i style={{ background: "var(--dn)" }} />10th percentile (average of 3 models, from {new Date(d.fan.origin * 1000).toISOString().slice(0, 10)}{d.fan.stale_days > 1 ? `, ${d.fan.stale_days} days behind` : ""}; they did not beat a random walk)</span>}
          {layers.signals && <span>▲▼ the daily trend rule turning on or off</span>}
        </div>
      )}
    </div>
  );
}
