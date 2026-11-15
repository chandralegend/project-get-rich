import { useEffect, useState } from "react";
import { get, post, useApi, Json } from "../api";
import { go } from "../App";
import { ActionButton, Card, Empty, fmt, Loading, Pill, Table, tone } from "../ui";

const CLASSES = [["crypto", "Crypto"], ["fx", "Forex"], ["metal", "Gold & silver"]] as const;
const actionTone = (a: string) => (a === "open_long" ? "up" : a === "open_short" ? "warn" : a === "exit" || a === "reduce" ? "dn" : "") as "" | "up" | "dn" | "warn";

function RunPanel({ onFinished }: { onFinished: () => void }) {
  const [classes, setClasses] = useState<string[]>(["crypto"]);
  const [refresh, setRefresh] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const jobs = useApi("/api/jobs", 4000);
  const running = (jobs.data?.jobs ?? []).find((j: Json) => j.kind === "trader" && j.status === "running");
  const shown = jobId ?? running?.id ?? (jobs.data?.jobs ?? []).find((j: Json) => j.kind === "trader")?.id ?? null;
  const job = useApi(shown ? `/api/jobs/${shown}` : null, running || (shown && jobId) ? 2500 : 0);
  const status = job.data?.status;
  useEffect(() => { if (status === "done") onFinished(); }, [status]);

  return (
    <Card title="Run the trader" right={<span className="note">about $0.05–0.10 per run, manual only</span>}>
      <div className="row">
        {CLASSES.map(([id, label]) => (
          <button key={id} className={`chip ${classes.includes(id) ? "on" : ""}`} onClick={() => setClasses((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))}>{label}</button>
        ))}
        <span className="sp" />
        <ActionButton className="btn primary" label={running ? "Running…" : "Run trader"} disabled={!!running || classes.length === 0} run={() => post("/api/trader/run", { classes, refresh })} onDone={(m) => setJobId(m.id)} />
      </div>
      <label className="row note" style={{ marginTop: 8, gap: 6 }}><input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} />Fetch the latest prices and news first, and classify the news (adds about a minute or two; untick to plan on what is already stored)</label>
      <div className="note" style={{ marginTop: 8 }}>Shadow mode: it reads the whole desk, writes a plan and checks each idea against the risk gate. Nothing becomes an order until you press <b>Propose to gate</b> on an idea and then approve it on Orders &amp; risk. </div>
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


const hrs = (h: number | null | undefined) => (h == null ? "–" : h < 1 ? `${Math.round(h * 60)} min` : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} days`);
const staleTone = (h: number | null | undefined, limit: number) => (h == null ? "" : h > limit ? "dn" : "up");

function Inputs({ pref }: { pref: string }) {
  const q = useApi(`/api/trader/packet/${pref}`, 0);
  if (q.error) return <Card title="Inputs it was given"><div className="note">The stored packet could not be loaded.</div></Card>;
  if (!q.data) return <Card title="Inputs it was given"><Loading error={q.error} /></Card>;
  const pk = q.data.packet, f = pk.freshness;
  const fc = Object.entries(pk.markets ?? {}).filter(([, m]: [string, any]) => m.forecasts && Object.keys(m.forecasts).length);
  const steps: [string, Json][] = Object.entries(f?.refresh_before_this_run?.steps ?? {});
  return (
    <Card title="Inputs it was given" right={<span className="note">as of {pk.as_of_utc} UTC</span>}>
      {!f ? <div className="note">This plan was made before freshness was recorded.</div> : (
        <table><tbody>
          <tr><td className="mu">Prices (hourly bar age)</td><td className={`r num ${staleTone(f.market_data?.hourly_bar_age_hours?.oldest, 3)}`}>{f.market_data?.hourly_bar_age_hours ? `${hrs(f.market_data.hourly_bar_age_hours.newest)} – ${hrs(f.market_data.hourly_bar_age_hours.oldest)}` : "–"}</td></tr>
          <tr><td className="mu">Newest story</td><td className={`r num ${staleTone(f.news?.newest_story_hours_ago, 3)}`}>{hrs(f.news?.newest_story_hours_ago)} ago</td></tr>
          <tr><td className="mu">Newest classified event</td><td className={`r num ${staleTone(f.news?.newest_classified_event_hours_ago, 3)}`}>{hrs(f.news?.newest_classified_event_hours_ago)} ago</td></tr>
          <tr><td className="mu">Recent stories not yet classified</td><td className={`r num ${f.news?.stories_from_last_24h_not_yet_classified > 20 ? "dn" : ""}`}>{f.news?.stories_from_last_24h_not_yet_classified}</td></tr>
          <tr><td className="mu">Briefing</td><td className={`r num ${staleTone(f.news?.briefing_hours_old, 12)}`}>{hrs(f.news?.briefing_hours_old)} old</td></tr>
        </tbody></table>
      )}
      {steps.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="note"><b>Refresh before this run</b></div>
          {steps.map(([k, v]) => <div key={k} className="note"><span className={v.ok ? "up" : "dn"}>{v.ok ? "ok" : "failed"}</span> {k.replace(/_/g, " ")} · {v.seconds}s{v.error ? ` · ${v.error}` : ""}</div>)}
        </div>
      )}
      {f && !f.refresh_before_this_run?.steps && <div className="note" style={{ marginTop: 6 }}>No refresh ran before this plan; it used what was stored.</div>}
      <div style={{ marginTop: 10 }}>
        <div className="note"><b>Forecasters</b> (BTC and ETH only; they did not beat a random walk)</div>
        {fc.length === 0 ? <div className="note">No forecasts in this plan.</div> : fc.map(([sym, m]: [string, any]) => (
          <div key={sym} style={{ marginTop: 4 }}>
            <div className="note"><b>{sym}</b></div>
            <table><tbody>{Object.entries(m.forecasts).map(([name, v]: [string, any]) => (
              <tr key={name}><td className="mu">{name}</td><td className="r num">{v.prob_up ? Object.entries(v.prob_up).map(([h, p]) => `${h} ${Math.round((p as number) * 100)}%`).join(" · ") : v.note ?? v.error}{v.stale ? " (stale)" : ""}<span className="mu"> · origin {v.origin}</span></td></tr>
            ))}</tbody></table>
          </div>
        ))}
        <div className="note" style={{ marginTop: 6 }}>Probability of an up move. These caches come from the research environment and are not refreshed by a run.</div>
      </div>
      <div className="note" style={{ marginTop: 8 }}><b>PI-Net:</b> {f?.pinet ?? "not an input."}</div>
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
            {plan.packet_ref && <Inputs key={plan.packet_ref} pref={plan.packet_ref} />}
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
