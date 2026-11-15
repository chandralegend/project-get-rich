import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import { useApi, Json } from "../api";
import { go } from "../App";
import { Card, ClassPill, Empty, fmt, Loading, Pill, tone } from "../ui";

function cssVar(name: string) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function Chart({ symbol, timeframe }: { symbol: string; timeframe: "1h" | "1d" }) {
  const ref = useRef<HTMLDivElement>(null);
  const bars = useApi(`/api/bars/${symbol}?timeframe=${timeframe}&limit=${timeframe === "1h" ? 400 : 365}`, 60000);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const c = createChart(ref.current, {
      height: 340, autoSize: true,
      layout: { background: { color: "transparent" }, textColor: cssVar("--mu") || "#8b929c" },
      grid: { vertLines: { color: cssVar("--line") || "#1c222a" }, horzLines: { color: cssVar("--line") || "#1c222a" } },
      rightPriceScale: { borderColor: cssVar("--line2") || "#2a323c" }, timeScale: { borderColor: cssVar("--line2") || "#2a323c", timeVisible: timeframe === "1h" },
      crosshair: { mode: 0 },
    });
    const s = c.addCandlestickSeries({ upColor: cssVar("--up") || "#3ddc97", downColor: cssVar("--dn") || "#ff6b6b", borderVisible: false, wickUpColor: cssVar("--up") || "#3ddc97", wickDownColor: cssVar("--dn") || "#ff6b6b" });
    chart.current = c; series.current = s;
    return () => { c.remove(); chart.current = null; series.current = null; };
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!series.current || !bars.data) return;
    series.current.setData(bars.data.bars.map((b: Json) => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })));
    chart.current?.timeScale().fitContent();
  }, [bars.data]);

  return <div>{!bars.data && <Loading error={bars.error} />}<div ref={ref} style={{ minHeight: bars.data ? 340 : 0 }} /></div>;
}

function Detail({ symbol }: { symbol: string }) {
  const [tf, setTf] = useState<"1h" | "1d">("1h");
  const d = useApi(`/api/instrument/${symbol}`, 60000);
  const x = d.data;
  return (
    <div className="grid g21">
      <Card title={<>{symbol}{x && <span className="mu" style={{ textTransform: "none", letterSpacing: 0 }}>{x.name}</span>}</>} right={<span className="row">{(["1h", "1d"] as const).map((t) => <button key={t} className={`chip ${tf === t ? "on" : ""}`} style={{ padding: "1px 10px" }} onClick={() => setTf(t)}>{t}</button>)}</span>}>
        <Chart symbol={symbol} timeframe={tf} />
      </Card>
      <div className="grid" style={{ alignContent: "start" }}>
        {!x ? <Card><Loading error={d.error} /></Card> : (
          <>
            <Card title="Right now" right={x.market_open ? <Pill tone="up">market open</Pill> : <Pill tone="warn">market closed</Pill>}>
              {x.hourly?.price == null ? <Empty>No recent hourly data.</Empty> : (
                <table><tbody>
                  <tr><td className="mu">Price</td><td className="r num">{fmt.price(x.hourly.price)}</td></tr>
                  <tr><td className="mu">1h / 4h / 24h</td><td className="r num"><span className={tone(x.hourly.ret_1h)}>{fmt.pct(x.hourly.ret_1h, 2, true)}</span> · <span className={tone(x.hourly.ret_4h)}>{fmt.pct(x.hourly.ret_4h, 2, true)}</span> · <span className={tone(x.hourly.ret_24h)}>{fmt.pct(x.hourly.ret_24h, 2, true)}</span></td></tr>
                  <tr><td className="mu">7d / 20d</td><td className="r num"><span className={tone(x.hourly.ret_7d)}>{fmt.pct(x.hourly.ret_7d, 1, true)}</span> · <span className={tone(x.daily.ret_20d)}>{fmt.pct(x.daily.ret_20d, 1, true)}</span></td></tr>
                  <tr><td className="mu">Volatility (24h / 20d)</td><td className="r num">{fmt.pct(x.hourly.realised_vol_24h_annual, 0)} / {fmt.pct(x.daily.vol_20d_annual, 0)}</td></tr>
                  <tr><td className="mu">ATR (24h)</td><td className="r num">{fmt.pct(x.hourly.atr_24h_pct_of_price, 2)}</td></tr>
                  <tr><td className="mu">Range position 24h / 7d</td><td className="r num">{x.hourly.range_position_24h} / {x.hourly.range_position_7d}</td></tr>
                  <tr><td className="mu">Stretch vs 48h mean</td><td className="r num">{x.hourly.state_facts.z_vs_48h_mean}σ</td></tr>
                  <tr><td className="mu">Hourly EMA12 &gt; EMA48</td><td className="r">{x.hourly.state_facts.ema12_above_ema48 ? "yes" : "no"}</td></tr>
                  <tr><td className="mu">Daily trend votes</td><td className="r num">{x.daily.trend_votes_of_3} of 3</td></tr>
                  <tr><td className="mu">From 90d high</td><td className="r num dn">{fmt.pct(x.daily.drawdown_from_90d_high, 1)}</td></tr>
                  <tr><td className="mu">Round-trip cost</td><td className="r num">{x.round_trip_cost_pct}%</td></tr>
                </tbody></table>
              )}
            </Card>
            <Card title="Levels"><table><tbody>
              <tr><td className="mu">24h high / low</td><td className="r num">{fmt.price(x.hourly.levels?.high_24h)} / {fmt.price(x.hourly.levels?.low_24h)}</td></tr>
              <tr><td className="mu">7d high / low</td><td className="r num">{fmt.price(x.hourly.levels?.high_7d)} / {fmt.price(x.hourly.levels?.low_7d)}</td></tr>
              <tr><td className="mu">Prior day high / low</td><td className="r num">{fmt.price(x.daily.prior_day_high)} / {fmt.price(x.daily.prior_day_low)}</td></tr>
              <tr><td className="mu">30d high / low</td><td className="r num">{fmt.price(x.daily.high_30d)} / {fmt.price(x.daily.low_30d)}</td></tr>
            </tbody></table></Card>
            {x.forecasts && (
              <Card title="Forecasters" right={<span className="note">none beat a random walk</span>}>
                <table><tbody>{Object.entries(x.forecasts).map(([m, v]: [string, any]) => (
                  <tr key={m}><td className="mu">{m}</td><td className="r num">{v.prob_up ? `${Object.entries(v.prob_up).map(([h, p]) => `${h} ${Math.round((p as number) * 100)}%`).join(" · ")}` : v.note ?? v.error}{v.stale && " (stale)"}</td></tr>
                ))}</tbody></table>
                <div className="note" style={{ marginTop: 6 }}>Probability of an up move. Tested walk-forward and found to be noise, so read these as a curiosity.</div>
              </Card>
            )}
            {x.note && <div className="note">{x.note}</div>}
          </>
        )}
      </div>
    </div>
  );
}

type SortKey = "symbol" | "ret_24h" | "ret_7d" | "move_24h_in_daily_sigmas" | "vol_20d_annual" | "trend_votes_of_3" | "range_position_7d" | "z_vs_48h_mean";

export default function Markets({ symbol }: { symbol: string }) {
  const uni = useApi("/api/universe", 60000);
  const [cls, setCls] = useState("all");
  const [sort, setSort] = useState<{ k: SortKey; dir: 1 | -1 }>({ k: "symbol", dir: 1 });
  const rows: Json[] = useMemo(() => {
    const r = (uni.data?.rows ?? []).filter((x: Json) => cls === "all" || x.class === cls);
    return [...r].sort((a, b) => ((a[sort.k] ?? -1e9) > (b[sort.k] ?? -1e9) ? 1 : -1) * sort.dir);
  }, [uni.data, cls, sort]);
  const th = (k: SortKey, label: string, right = true) => <th className={`sort ${right ? "r" : ""}`} onClick={() => setSort((s) => ({ k, dir: s.k === k ? (-s.dir as 1 | -1) : -1 }))}>{label}{sort.k === k ? (sort.dir === 1 ? " ↑" : " ↓") : ""}</th>;

  return (
    <>
      {symbol && <><div className="row"><button className="btn sm" onClick={() => go("markets")}>← All instruments</button></div><Detail symbol={symbol} /></>}
      <Card title="Universe" right={<span className="row">{["all", "crypto", "fx", "metal"].map((c) => <button key={c} className={`chip ${cls === c ? "on" : ""}`} style={{ padding: "1px 10px" }} onClick={() => setCls(c)}>{c}</button>)}</span>}>
        {!uni.data ? <Loading error={uni.error} /> : (
          <div className="scroll"><table>
            <thead><tr>{th("symbol", "Instrument", false)}<th>Class</th><th className="r">Price</th>{th("ret_24h", "24h")}{th("ret_7d", "7d")}{th("move_24h_in_daily_sigmas", "24h in σ")}{th("vol_20d_annual", "Vol")}{th("trend_votes_of_3", "Trend")}{th("range_position_7d", "7d range")}{th("z_vs_48h_mean", "Stretch")}<th className="r">Cost</th><th className="r">Min stop</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((r) => r.available ? (
                <tr key={r.symbol} className="click" onClick={() => go("markets", r.symbol)} style={r.symbol === symbol ? { background: "var(--s2)" } : undefined}>
                  <td><b>{r.symbol}</b><div className="note">{r.name}</div></td><td><ClassPill c={r.class} /></td><td className="r num">{fmt.price(r.price)}</td>
                  <td className={`r num ${tone(r.ret_24h)}`}>{fmt.pct(r.ret_24h, 2, true)}</td><td className={`r num ${tone(r.ret_7d)}`}>{fmt.pct(r.ret_7d, 1, true)}</td>
                  <td className={`r num ${tone(r.move_24h_in_daily_sigmas)}`}>{r.move_24h_in_daily_sigmas?.toFixed(2)}</td><td className="r num">{fmt.pct(r.vol_20d_annual, 0)}</td>
                  <td className="r num">{r.trend_votes_of_3}/3</td><td className="r num">{r.range_position_7d?.toFixed(2)}</td><td className="r num">{r.z_vs_48h_mean?.toFixed(1)}σ</td>
                  <td className="r num dim">{r.round_trip_cost_pct}%</td><td className="r num dim">{r.min_stop_pct}%</td>
                  <td>{r.can_open_now ? <Pill tone="up">tradable</Pill> : !r.market_open ? <Pill tone="warn">closed</Pill> : <Pill tone="warn">stale</Pill>}</td>
                </tr>
              ) : (
                <tr key={r.symbol}><td><b>{r.symbol}</b><div className="note">{r.name}</div></td><td><ClassPill c={r.class} /></td><td colSpan={11} className="dim">{r.why}</td></tr>
              ))}
            </tbody>
          </table></div>
        )}
        {(uni.data?.no_data_yet?.length ?? 0) > 0 && <div className="note" style={{ marginTop: 8 }}>No data yet for {uni.data?.no_data_yet.join(", ")}: refresh market data on the System screen.</div>}
      </Card>
    </>
  );
}
