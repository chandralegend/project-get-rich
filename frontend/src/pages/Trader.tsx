import { useEffect, useState } from "react";
import { get, post, useApi, Json } from "../api";
import { go } from "../App";
import { ActionButton, Card, Empty, fmt, Loading, Pill, Table, tone } from "../ui";

const CLASSES = [["crypto", "Crypto"], ["fx", "Forex"], ["metal", "Gold & silver"]] as const;
const actionTone = (a: string) => (a === "open_long" ? "up" : a === "open_short" ? "warn" : a === "exit" || a === "reduce" ? "dn" : "") as "" | "up" | "dn" | "warn";

function RunPanel({ onFinished }: { onFinished: () => void }) {
  const [classes, setClasses] = useState<string[]>(["crypto"]);
  const [jobId, setJobId] = useState<string | null>(null);
  const jobs = useApi("/api/jobs", 4000);
  const running = (jobs.data?.jobs ?? []).find((j: Json) => j.kind === "trader" && j.status === "running");
  const shown = jobId ?? running?.id ?? (jobs.data?.jobs ?? []).find((j: Json) => j.kind === "trader")?.id ?? null;
  const job = useApi(shown ? `/api/jobs/${shown}` : null, running || (shown && jobId) ? 2500 : 0);
  const status = job.data?.status;
  useEffect(() => { if (status === "done") onFinished(); }, [status]);

  return (
    <Card title="Run the trader" right={<span className="note">about $0.05 per run, manual only</span>}>
      <div className="row">
        {CLASSES.map(([id, label]) => (
          <button key={id} className={`chip ${classes.includes(id) ? "on" : ""}`} onClick={() => setClasses((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))}>{label}</button>
        ))}
        <span className="sp" />
        <ActionButton className="btn primary" label={running ? "Running…" : "Run trader"} disabled={!!running || classes.length === 0} run={() => post("/api/trader/run", { classes })} onDone={(m) => setJobId(m.id)} />
      </div>
      <div className="note" style={{ marginTop: 8 }}>Shadow mode: it reads the whole desk, writes a plan and checks each idea against the risk gate. Nothing becomes an order until you press <b>Propose to gate</b> on an idea and then approve it on Orders &amp; risk. Refresh market data on the System screen first if it is stale.</div>
      {job.data && (
        <div style={{ marginTop: 10 }}>
          <div className="row"><Pill tone={status === "done" ? "up" : status === "running" ? "ac" : "dn"}>{status}</Pill><span className="note">started {fmt.ago(job.data.started)}</span></div>
          {status !== "done" && <pre className="log" style={{ marginTop: 8 }}>{job.data.tail || "waiting for output…"}</pre>}
          {status === "failed" && <div className="dn" style={{ marginTop: 6 }}>The run failed. The log above says why (a missing key, a budget cap, or stale data are the usual reasons).</div>}
        </div>
      )}
    </Card>
  );
}

function Idea({ it, onProposed }: { it: Json; onProposed: (r: Json) => void }) {
  const w = it.gate_whatif;
  const canPropose = (it.action === "open_long" || it.action === "exit" || it.action === "reduce") && it.tradable && !it.outcome;
  return (
    <div className="idea">
      <div className="h">
        <b>{it.instrument}</b><Pill tone={actionTone(it.action)}>{it.action.replace("_", " ")}</Pill><Pill>{it.setup.replace(/_/g, " ")}</Pill>
        <span className="note">conviction</span><span className="bar" style={{ width: 70 }}><i style={{ width: `${Math.round(it.conviction * 100)}%` }} /></span><span className="num mu">{it.conviction.toFixed(2)}</span>
        {it.action === "open_short" && <Pill tone="warn">hypothetical</Pill>}
        <span className="sp" />
        {canPropose && <ActionButton className="btn sm primary" label="Propose to gate" run={() => post(`/api/ideas/${it.insight_id}/propose`)} onDone={onProposed} />}
      </div>
      <div>{it.thesis}</div>
      <div className="note"><b>Wrong if:</b> {it.invalidation}</div>
      {(it.action === "open_long" || it.action === "open_short") && (
        <div className="row note num"><span>entry ~{fmt.price(it.price_at_issue)}</span><span>stop {fmt.pct(it.stop_pct, 2)}</span><span>target {it.target_pct ? fmt.pct(it.target_pct, 2) : "none"}</span><span>hold ≤ {it.max_hold_hours}h</span><span>risk {fmt.pct(it.risk_fraction, 2)}</span></div>
      )}
      {w && <div className="note">{w.approved ? <span className="up">Gate would approve: {w.qty} units, ${w.notional?.toFixed(2)} notional, ${w.risk_amount?.toFixed(2)} at risk.</span> : <span className="dn">Gate would refuse: {w.reasons?.join("; ")}</span>}</div>}
      {it.outcome && it.outcome !== "not scored" && <div className="note">Outcome: <span className={tone(it.outcome.r)}>{it.outcome.r?.toFixed(2)}R</span> ({it.outcome.kind}, {it.outcome.bars}h, net {fmt.pct(it.outcome.net_return, 2, true)})</div>}
      {it.outcome == null && ["open_long", "open_short"].includes(it.action) && <div className="note">Outcome pending: scored against the hourly bars after it was issued.</div>}
    </div>
  );
}

export default function Trader() {
  const plans = useApi("/api/trader/plans?limit=10", 20000);
  const [sel, setSel] = useState(0);
  const [packet, setPacket] = useState<Json | null>(null);
  const [proposed, setProposed] = useState<Json | null>(null);
  if (!plans.data) return <Loading error={plans.error} />;
  const list: Json[] = plans.data.plans, plan = list[sel], card = plans.data.card;

  return (
    <>
      <RunPanel onFinished={() => { plans.reload(); setSel(0); }} />
      {proposed && (
        <div className={`banner ${proposed.verdict.approved ? "warn" : "dn"}`}>
          {proposed.verdict.approved ? <><b>Proposal created.</b><span>{proposed.verdict.qty} units, gate approved. It expires in 15 minutes.</span><button className="btn sm primary" onClick={() => go("orders")}>Review and approve</button></> : <><b>The gate refused it:</b><span>{proposed.verdict.reasons.join("; ")}</span></>}
          <span className="sp" /><button className="btn sm" onClick={() => setProposed(null)}>Dismiss</button>
        </div>
      )}
      {!plan ? <Card><Empty>No plans yet. Run the trader above.</Empty></Card> : (
        <div className="grid g21">
          <div className="grid">
            <Card title={<>Plan · {fmt.time(plan.as_of)}</>} right={<span className="note">{fmt.ago(plan.as_of)} · ${plan.cost_usd?.toFixed(3)}</span>}>
              <div className="row" style={{ marginBottom: 8 }}>
                <Pill tone={plan.regime === "stressed" ? "dn" : plan.regime.startsWith("trending") ? "ac" : ""}>{plan.regime}</Pill>
                <Pill>{plan.stance.risk_posture}</Pill><span className="note">cash target {fmt.pct(plan.stance.cash_target_fraction, 0)}</span>
              </div>
              <p style={{ margin: "0 0 10px" }}>{plan.narrative}</p>
              <div className="banner" style={{ marginBottom: 10 }}><b>Edge check</b><span>{plan.edge_check}</span></div>
              <div className="note" style={{ marginBottom: 4 }}><b>What it looked at and passed on.</b></div>
              <p style={{ margin: "0 0 4px" }}>{plan.universe_view}</p>
            </Card>
            <Card title={`Ideas (${plan.ideas.length})`}>
              {plan.ideas.length === 0 ? <Empty>No ideas kept in this plan.</Empty> : <div className="grid" style={{ gap: 10 }}>{plan.ideas.map((i: Json) => <Idea key={i.insight_id} it={i} onProposed={setProposed} />)}</div>}
              {plan.dropped?.length > 0 && <div className="note" style={{ marginTop: 10 }}>Corrected by validation: {plan.dropped.join(" · ")}</div>}
            </Card>
            <div className="grid g2">
              <Card title="Main risks"><ul style={{ margin: 0, paddingLeft: 18 }}>{plan.main_risks.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></Card>
              <Card title="Watchlist"><ul style={{ margin: 0, paddingLeft: 18 }}>{plan.watchlist.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></Card>
            </div>
            <Card title="Review of its past calls"><p style={{ margin: 0 }}>{plan.review_of_past_calls}</p></Card>
            <Card title="What it saw" right={plan.packet_ref && <button className="btn sm" onClick={async () => setPacket(packet ? null : await get(`/api/trader/packet/${plan.packet_ref}`))}>{packet ? "Hide" : "Show the exact input"}</button>}>
              {packet ? <pre className="log" style={{ maxHeight: 420 }}>{JSON.stringify(packet.packet, null, 1)}</pre> : <div className="note">The exact desk packet is stored with the plan, so you can always check what the agent was shown.</div>}
            </Card>
          </div>
          <div className="grid" style={{ alignContent: "start" }}>
            <Card title="Its track record" right={<span className="note">forward, in shadow</span>}>
              {card.ideas_scored === 0 ? <Empty>No scored ideas yet. Only open ideas are scored; waiting is not.</Empty> : (
                <table><tbody>
                  <tr><td className="mu">Open ideas scored</td><td className="r num">{card.ideas_scored} ({card.pending} pending)</td></tr>
                  <tr><td className="mu">Win rate</td><td className="r num">{card.resolved.n ? fmt.pct(card.resolved.win_rate, 0) : "–"}</td></tr>
                  <tr><td className="mu">Average R</td><td className={`r num ${tone(card.resolved.avg_r)}`}>{card.resolved.n ? card.resolved.avg_r : "–"}</td></tr>
                  <tr><td className="mu">Stops / targets / timeouts</td><td className="r num">{card.stops} / {card.targets} / {card.timeouts}</td></tr>
                </tbody></table>
              )}
              <div className="note" style={{ marginTop: 8 }}>Decisions so far: {Object.entries(card.by_action).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(", ") || "none"}. Nothing earns trust below about 100 resolved ideas.</div>
            </Card>
            <Card title="History">
              <Table head={<><th>When</th><th>Regime</th><th className="r">Ideas</th></>}>
                {list.map((p, i) => (
                  <tr key={p.plan_id} className="click" onClick={() => { setSel(i); setPacket(null); }} style={i === sel ? { background: "var(--s2)" } : undefined}>
                    <td>{fmt.time(p.as_of)}</td><td>{p.regime}</td><td className="r num">{p.ideas.length}</td>
                  </tr>
                ))}
              </Table>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
