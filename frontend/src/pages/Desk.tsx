import { useApi, Json } from "../api";
import { go } from "../App";
import { Card, ClassPill, Empty, fmt, Kpi, Loading, Pill, Sparkline, Table, tone } from "../ui";

export default function Desk({ ov, err }: { ov: Json | null; err: string | null }) {
  const uni = useApi("/api/universe", 60000);
  if (!ov) return <Loading error={err} />;
  const p = ov.portfolio, plan = ov.last_plan, start = ov.start_equity;
  const curve: number[] = (ov.equity_curve ?? []).map((x: Json) => x.equity);
  const rows: Json[] = (uni.data?.rows ?? []).filter((r: Json) => r.available);
  const pnl = p.equity / start - 1;

  return (
    <>
      {(p.halted || p.killed) && (
        <div className="banner dn"><b>{p.killed ? "Kill switch is on." : "Drawdown halt is latched."}</b><span className="note">No new positions can open until you clear it on the Orders &amp; risk screen.</span><span className="sp" /><button className="btn" onClick={() => go("orders")}>Open</button></div>
      )}
      <div className="kpis">
        <Kpi label="Equity" value={fmt.usd(p.equity)} sub={<span className={tone(pnl)}>{fmt.pct(pnl, 2, true)} since start ({fmt.usd(start, 0)})</span>} />
        <Kpi label="Cash" value={fmt.usd(p.cash)} sub={`exposure ${fmt.pct(p.exposure_fraction, 0)} of equity`} />
        <Kpi label="Drawdown" value={fmt.pct(p.drawdown_from_peak, 1)} cls={p.drawdown_from_peak > 0.05 ? "warn" : ""} sub={`halt at ${fmt.pct(p.limits?.account_drawdown_halt, 0)}`} />
        <Kpi label="Today" value={fmt.pct(p.today_pnl_fraction, 2, true)} cls={tone(p.today_pnl_fraction)} sub={`daily halt ${fmt.pct(p.limits?.daily_loss_halt, 1)}`} />
        <Kpi label="Claude this month" value={fmt.usd(ov.budget.spent, 2)} sub={`cap ${fmt.usd(ov.budget.cap, 0)}`} />
      </div>

      <div className="grid g21">
        <Card title="Equity" right={<span className="note">{curve.length} snapshots</span>}><Sparkline values={curve} height={150} /></Card>
        <Card title="Limits in force" right={<Pill tone="ac">{p.limits?.profile ?? "unpinned"}</Pill>}>
          {p.limits?.profile ? (
            <table><tbody>
              <tr><td className="mu">Max exposure</td><td className="r num">{fmt.pct(p.limits.max_exposure_fraction, 0)}</td></tr>
              <tr><td className="mu">Risk per trade</td><td className="r num">{fmt.pct(p.limits.risk_per_trade, 1)}</td></tr>
              <tr><td className="mu">Leverage</td><td className="r num">{p.limits.max_leverage}x</td></tr>
              <tr><td className="mu">Shorting</td><td className="r">{p.limits.allow_short ? "allowed" : "off"}</td></tr>
            </tbody></table>
          ) : <Empty>Limits are not pinned: the gate refuses every entry.</Empty>}
        </Card>
      </div>

      <div className="grid g2">
        <Card title="Positions" right={<a href="#/orders">orders &amp; risk</a>}>
          {p.positions.length === 0 ? <Empty>Flat. No open positions.</Empty> : (
            <Table head={<><th>Symbol</th><th className="r">Qty</th><th className="r">Entry</th><th className="r">Mark</th><th className="r">P&amp;L</th><th className="r">Stop</th></>}>
              {p.positions.map((x: Json) => (
                <tr key={x.symbol} className="click" onClick={() => go("markets", x.symbol)}>
                  <td><b>{x.symbol}</b></td><td className="r num">{x.qty}</td><td className="r num">{fmt.price(x.avg_price)}</td><td className="r num">{fmt.price(x.mark)}</td>
                  <td className={`r num ${tone(x.unrealised_pct)}`}>{fmt.pct(x.unrealised_pct, 2, true)}</td><td className="r num dim">{fmt.price(x.stop)}</td>
                </tr>
              ))}
            </Table>
          )}
          {p.pending_proposals.length > 0 && <div className="banner warn" style={{ marginTop: 10 }}><b>{p.pending_proposals.length} proposal(s) waiting for you.</b><span className="sp" /><button className="btn sm" onClick={() => go("orders")}>Review</button></div>}
        </Card>

        <Card title="Latest trader plan" right={plan ? <span className="note">{fmt.ago(plan.as_of)}</span> : <a href="#/trader">open trader</a>}>
          {!plan ? <Empty>No plan yet. Run the trader from the Trader screen.</Empty> : (
            <div className="grid" style={{ gap: 8 }}>
              <div className="row"><Pill tone={plan.regime === "stressed" ? "dn" : plan.regime?.startsWith("trending") ? "ac" : ""}>{plan.regime}</Pill><Pill>{plan.stance.risk_posture}</Pill><span className="note">cash target {fmt.pct(plan.stance.cash_target_fraction, 0)}</span></div>
              <div className="note" style={{ color: "var(--tx)" }}>{plan.edge_check}</div>
              <div className="row">{plan.ideas.length === 0 ? <span className="note">No ideas kept.</span> : plan.ideas.map((i: Json) => <Pill key={i.insight_id} tone={i.action === "open_long" ? "up" : i.action === "wait" ? "" : "ac"}>{i.instrument} {i.action.replace("_", " ")}</Pill>)}</div>
              <a href="#/trader">Read the full plan</a>
            </div>
          )}
        </Card>
      </div>

      <Card title="Market snapshot" right={<span className="note">24h move · click for chart</span>}>
        {rows.length === 0 ? <Loading error={uni.error} /> : (
          <div className="heat">
            {rows.map((r) => (
              <div key={r.symbol} onClick={() => go("markets", r.symbol)} title={`${r.name}${r.can_open_now ? "" : " (closed or stale)"}`} style={{ opacity: r.can_open_now ? 1 : 0.5 }}>
                <b>{r.symbol.replace("USDT", "")}</b>
                <span className={`num ${tone(r.ret_24h)}`}>{fmt.pct(r.ret_24h, 2, true)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {ov.alerts.length > 0 && (
        <Card title="Active alerts">
          {ov.alerts.map((a: Json) => <div key={a.key} className="row" style={{ padding: "4px 0" }}><Pill tone={a.severity === "P0" ? "dn" : "warn"}>{a.severity}</Pill><span>{a.message}</span><span className="note">{a.action}</span></div>)}
        </Card>
      )}
    </>
  );
}
