import { useState } from "react";
import { post, useApi, Json } from "../api";
import { ActionButton, Card, Confirm, Empty, fmt, Loading, Pill, Table } from "../ui";

const statusTone = (s: string) => (s === "filled" || s === "closed" ? "up" : s === "proposed" ? "warn" : s.startsWith("rejected") || s === "failed" || s === "expired" ? "dn" : "") as "" | "up" | "dn" | "warn";

export default function Orders() {
  const o = useApi("/api/orders?limit=60", 10000);
  const [confirm, setConfirm] = useState<null | "kill" | "unhalt" | "unkill">(null);
  const [note, setNote] = useState<string | null>(null);
  if (!o.data) return <Loading error={o.error} />;
  const d = o.data, pending: Json[] = d.orders.filter((x: Json) => x.status === "proposed");
  const lim = d.limits;
  const act = async (path: string) => { const r = await post(path); o.reload(); return r; };

  return (
    <>
      {note && <div className="banner warn"><span>{note}</span><span className="sp" /><button className="btn sm" onClick={() => setNote(null)}>Dismiss</button></div>}
      <div className="grid g21">
        <Card title="Proposals waiting for you" right={<span className="note">approve within 15 minutes or they expire</span>}>
          {pending.length === 0 ? <Empty>Nothing waiting. Proposals come from the Trader screen.</Empty> : (
            <div className="grid" style={{ gap: 10 }}>
              {pending.map((x) => {
                const v = JSON.parse(x.verdict || "{}");
                return (
                  <div key={x.order_id} className="idea">
                    <div className="h"><b>{x.symbol}</b><Pill tone={x.side === "buy" ? "up" : "dn"}>{x.side}</Pill><span className="num">{x.qty} units</span><span className="note">created {fmt.ago(x.created_at)} by {x.source}</span></div>
                    <div className="note">{x.reason}</div>
                    <div className="row note num"><span>ref {fmt.price(x.ref_price)}</span><span>stop {fmt.price(x.stop_price)}</span><span>target {fmt.price(x.take_profit)}</span>{v.risk_amount != null && <span>risk ${v.risk_amount} ({fmt.pct(v.risk_fraction, 2)})</span>}{v.notional != null && <span>notional ${v.notional}</span>}</div>
                    <div className="row">
                      <ActionButton className="btn primary sm" label="Approve (paper fill)" run={() => act(`/api/orders/${x.order_id}/approve`)} onDone={(r) => !r.ok && setNote(r.note)} />
                      <ActionButton className="btn sm" label="Reject" run={() => act(`/api/orders/${x.order_id}/reject`)} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
        <div className="grid" style={{ alignContent: "start" }}>
          <Card title="Risk limits" right={lim.pinned ? <Pill tone="up">pinned</Pill> : <Pill tone="dn">not pinned</Pill>}>
            {!lim.pinned ? <Empty>{lim.why}</Empty> : <table><tbody>
              <tr><td className="mu">Profile</td><td className="r">{lim.profile}</td></tr>
              <tr><td className="mu">Max exposure</td><td className="r num">{fmt.pct(lim.max_exposure_fraction, 0)}</td></tr>
              <tr><td className="mu">Risk per trade</td><td className="r num">{fmt.pct(lim.risk_per_trade, 1)}</td></tr>
              <tr><td className="mu">Drawdown halt</td><td className="r num">{fmt.pct(lim.account_drawdown_halt, 0)}</td></tr>
              <tr><td className="mu">Daily loss halt</td><td className="r num">{fmt.pct(lim.daily_loss_halt, 1)}</td></tr>
              <tr><td className="mu">Leverage / shorting</td><td className="r">{lim.max_leverage}x / {lim.allow_short ? "allowed" : "off"}</td></tr>
            </tbody></table>}
            <div className="note" style={{ marginTop: 8 }}>Limits are hash-pinned. Changing them is your decision, made in the terminal with <span className="mono">limits-approve</span>, not here.</div>
          </Card>
          <Card title="Emergency controls">
            <div className="row"><Pill tone={d.killed ? "dn" : "up"}>kill switch {d.killed ? "ON" : "off"}</Pill><Pill tone={d.halted ? "dn" : "up"}>halt {d.halted ? "LATCHED" : "clear"}</Pill></div>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn danger" onClick={() => setConfirm("kill")}>Kill: flatten everything</button>
              {d.killed && <button className="btn" onClick={() => setConfirm("unkill")}>Lift kill switch</button>}
              {d.halted && <button className="btn" onClick={() => setConfirm("unhalt")}>Reset drawdown halt</button>}
            </div>
            <div className="note" style={{ marginTop: 8 }}>Equity {fmt.usd(d.equity)}, peak {fmt.usd(d.peak_equity)}. Exits are always allowed, even when halted.</div>
          </Card>
        </div>
      </div>

      <Card title="Open positions">
        {d.positions.length === 0 ? <Empty>Flat.</Empty> : (
          <Table head={<><th>Symbol</th><th className="r">Qty</th><th className="r">Entry</th><th className="r">Mark</th><th className="r">P&amp;L</th><th className="r">Stop</th><th className="r">Target</th><th className="r">At risk</th><th className="r">Age</th></>}>
            {d.positions.map((x: Json) => (
              <tr key={x.symbol}><td><b>{x.symbol}</b></td><td className="r num">{x.qty}</td><td className="r num">{fmt.price(x.avg_price)}</td><td className="r num">{fmt.price(x.mark)}</td><td className={`r num ${x.unrealised_pct >= 0 ? "up" : "dn"}`}>{fmt.pct(x.unrealised_pct, 2, true)}</td>
                <td className="r num">{fmt.price(x.stop)}</td><td className="r num">{fmt.price(x.take_profit)}</td><td className="r num">{fmt.usd(x.dollars_at_risk_to_stop)}</td><td className="r num">{x.age_hours}h</td></tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Order history">
        {d.orders.length === 0 ? <Empty>No orders yet.</Empty> : (
          <Table head={<><th>When</th><th>Symbol</th><th>Side</th><th className="r">Qty</th><th>Status</th><th>Source</th><th>Detail</th></>}>
            {d.orders.map((x: Json) => (
              <tr key={x.order_id}><td className="dim">{fmt.time(x.created_at)}</td><td><b>{x.symbol}</b></td><td>{x.side}</td><td className="r num">{x.qty}</td><td><Pill tone={statusTone(x.status)}>{x.status}</Pill></td><td className="dim">{x.source}</td><td className="note">{x.detail || x.reason}</td></tr>
            ))}
          </Table>
        )}
      </Card>

      {confirm === "kill" && <Confirm danger title="Flatten everything?" body="This sells every open position at the current price and blocks all new entries until you lift the kill switch. In paper mode nothing leaves this machine." confirm="Kill" onNo={() => setConfirm(null)} onYes={async () => { setConfirm(null); const r = await post("/api/risk/kill"); setNote(`Flattened: ${r.flattened.join(", ") || "nothing was open"}${r.errors.length ? `; errors: ${r.errors.join("; ")}` : ""}`); o.reload(); }} />}
      {confirm === "unkill" && <Confirm title="Lift the kill switch?" body="New entries become possible again." confirm="Lift" onNo={() => setConfirm(null)} onYes={async () => { setConfirm(null); await post("/api/risk/unkill"); o.reload(); }} />}
      {confirm === "unhalt" && <Confirm title="Reset the drawdown halt?" body="The halt tripped because the account fell by the limit. Reset it only after you have looked at why. New entries become possible again." confirm="Reset" onNo={() => setConfirm(null)} onYes={async () => { setConfirm(null); await post("/api/risk/unhalt"); o.reload(); }} />}
    </>
  );
}
