import { useEffect, useState } from "react";
import { get, post, useApi, Json } from "../api";
import { go } from "../App";
import { ActionButton, Card, Empty, fmt, Loading, Pill, Table, tone } from "../ui";
import { Gauge, InstrumentChart, MEANING, Triggers, Votes, Zone, ZONE_LABEL, triggerState, zoneColor } from "../visual";

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
        <div className="note" style={{ marginTop: 6 }}>Probability of an up move. A separate models service adds one forecast per model after each daily bar closes (see System); a trader run does not compute them.</div>
      </div>
      <div className="note" style={{ marginTop: 8 }}>
        <b>PI-Net</b> (frozen model, forward study, no demonstrated edge):{" "}
        {Object.entries(pk.markets ?? {}).filter(([, m]: [string, any]) => m.pinet?.call).map(([sym, m]: [string, any]) => `${sym} ${m.pinet.call.replace(/_/g, " ")}${m.pinet.expected_r != null ? ` (E[R] ${m.pinet.expected_r.toFixed(2)})` : ""}`).join(" · ") || "no decision in this plan's input."}
        {f?.pinet?.study && <> Study so far: {f.pinet.study.resolved} resolved, {f.pinet.study.note}.</>}
      </div>
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

/** The one-glance answer: what the trader says to do now, how our indicators lean across the whole universe, and what it is waiting for. */
function Hero({ plan, rows, prices, onFocus }: { plan: Json | undefined; rows: Json[]; prices: Record<string, number>; onFocus: (s: string) => void }) {
  const ideas: Json[] = plan?.ideas ?? [];
  const buys = ideas.filter((i) => i.action === "open_long" && i.tradable && i.gate_whatif?.approved && !i.outcome);
  const exits = ideas.filter((i) => ["exit", "reduce"].includes(i.action));
  const state = buys.length ? "BUY CANDIDATE" : exits.length ? "EXIT / REDUCE" : "WAIT";
  const color = buys.length ? "var(--up)" : exits.length ? "var(--dn)" : "var(--warn)";
  const zones = { buy: 0, wait: 0, avoid: 0, no_read: 0 } as Record<Zone, number>;
  rows.forEach((r) => { zones[(r.board?.zone ?? "no_read") as Zone] += 1; });
  const total = Math.max(1, rows.length);
  const trig: Json[] = (plan?.triggers ?? []).map((t: Json) => ({ ...t, st: triggerState(t, prices[t.instrument]) })).filter((t: Json) => t.st.dist != null && !t.st.met);
  const closest = [...trig].sort((a, b) => (a.meaning === "buy_candidate" ? 0 : 1) - (b.meaning === "buy_candidate" ? 0 : 1) || Math.abs(a.st.dist) - Math.abs(b.st.dist))[0];
  const ageMin = plan ? (Date.now() - new Date(plan.as_of).getTime()) / 60000 : null;
  return (
    <section className="card hero">
      <div className="hero-state" style={{ borderColor: color }}>
        <div className="hero-word" style={{ color }}>{state}</div>
        <div className="note">{!plan ? "No plan yet. Run the trader." : buys.length ? `${buys.map((b) => b.instrument).join(", ")}: the gate approved a size. Propose it below, then approve it on Orders.` : exits.length ? `Close or trim ${exits.map((b) => b.instrument).join(", ")}.` : `${plan.stance.risk_posture} · cash target ${fmt.pct(plan.stance.cash_target_fraction, 0)} · market ${plan.regime}`}</div>
        {plan && <div className={`note ${ageMin != null && ageMin > 360 ? "warn" : ""}`}>plan made {fmt.ago(plan.as_of)}{ageMin != null && ageMin > 360 ? " · old, run it again" : ""}</div>}
      </div>
      <div className="hero-tile">
        <div className="l">Our indicators across {rows.length} instruments</div>
        <div className="stack" role="img" aria-label={`${zones.buy} buy zone, ${zones.wait} wait, ${zones.avoid} avoid`}>
          <i style={{ width: `${(zones.buy / total) * 100}%`, background: "var(--up)" }} /><i style={{ width: `${(zones.wait / total) * 100}%`, background: "var(--warn)" }} /><i style={{ width: `${(zones.avoid / total) * 100}%`, background: "var(--dn)" }} /><i style={{ width: `${(zones.no_read / total) * 100}%`, background: "var(--line2)" }} />
        </div>
        <div className="row note num" style={{ gap: 12 }}><span style={{ color: "var(--up)" }}>{zones.buy} buy</span><span style={{ color: "var(--warn)" }}>{zones.wait} wait</span><span style={{ color: "var(--dn)" }}>{zones.avoid} avoid</span></div>
      </div>
      <div className="hero-tile">
        <div className="l">What it is waiting for</div>
        {!closest ? <div className="note">{plan ? "No open triggers in this plan." : "–"}</div> : (
          <button className="linkish" onClick={() => onFocus(closest.instrument)}>
            <div><b>{closest.instrument.replace("USDT", "")}</b> <span className="num">{closest.direction === "above" ? "↑" : "↓"} {fmt.price(closest.level)}</span></div>
            <div className="tbar"><i style={{ width: `${Math.max(0, Math.min(1, 1 - Math.abs(closest.st.dist) / 0.1)) * 100}%`, background: MEANING[closest.meaning]?.color ?? "var(--ac)" }} /></div>
            <div className="note">needs <b className="num">{fmt.pct(Math.abs(closest.st.dist), 1)}</b> {closest.direction === "above" ? "higher" : "lower"} · {MEANING[closest.meaning]?.label ?? closest.meaning}</div>
          </button>
        )}
      </div>
    </section>
  );
}

function MeterGrid({ rows, focus, onFocus, ideaBySym }: { rows: Json[]; focus: string | null; onFocus: (s: string) => void; ideaBySym: Record<string, Json> }) {
  const sorted = [...rows].sort((a, b) => (b.board?.score ?? -9) - (a.board?.score ?? -9));
  return (
    <div className="meters">
      {sorted.map((r) => {
        const b = r.board, z = (b?.zone ?? "no_read") as Zone, idea = ideaBySym[r.symbol];
        return (
          <button key={r.symbol} className={`meter ${focus === r.symbol ? "on" : ""}`} onClick={() => onFocus(r.symbol)} aria-label={`${r.symbol} ${ZONE_LABEL[z]}`}>
            <div className="row" style={{ gap: 6 }}><b>{r.symbol.replace("USDT", "")}</b><span className="sp" /><span className={`num ${tone(r.ret_24h)}`}>{fmt.pct(r.ret_24h, 1, true)}</span></div>
            <Gauge score={b?.score ?? null} zone={z} size="sm" buy={0.35} avoid={-0.35} />
            <div className="note num">{fmt.price(r.price)}</div>
            <div className="note num">{b ? <><span style={{ color: "var(--up)" }}>▲{b.up}</span> <span style={{ color: "var(--dn)" }}>▼{b.down}</span> <span>of {b.n}</span></> : "no data"}</div>
            {idea && <span className="mtag" style={{ color: idea.action === "open_long" ? "var(--up)" : "var(--mu)" }}>{idea.action === "open_long" ? "buy idea" : idea.action.replace("_", " ")}</span>}
          </button>
        );
      })}
    </div>
  );
}

function Focus({ symbol, row, plan, triggers, prices, onProposed }: { symbol: string; row: Json | undefined; plan: Json | undefined; triggers: Json[]; prices: Record<string, number>; onProposed: (r: Json) => void }) {
  const b = row?.board, z = (b?.zone ?? "no_read") as Zone;
  const idea = (plan?.ideas ?? []).find((i: Json) => i.instrument === symbol);
  return (
    <div className="grid g21">
      <div className="grid" style={{ alignContent: "start" }}>
        <Card title={<>{symbol}{row && <span className="mu" style={{ textTransform: "none", letterSpacing: 0 }}> {row.name}</span>}</>} right={row && <span className="num">{fmt.price(row.price)} <span className={tone(row.ret_24h)}>{fmt.pct(row.ret_24h, 2, true)}</span></span>}>
          <InstrumentChart symbol={symbol} triggers={triggers} />
        </Card>
        <Card title="The signals behind the needle" right={<span className="note">hover a row for what our tests found</span>}>
          {b ? <Votes votes={b.votes} /> : <Empty>No data for this instrument.</Empty>}
        </Card>
      </div>
      <div className="grid" style={{ alignContent: "start" }}>
        <Card title="Indicator agreement" right={<span className="note">not a forecast</span>}>
          <div className="row" style={{ justifyContent: "center" }}><Gauge score={b?.score ?? null} zone={z} size="lg" /></div>
          {b && <div className="row note num" style={{ justifyContent: "center", gap: 14, marginTop: 4 }}><span style={{ color: "var(--up)" }}>▲ {b.up} up</span><span style={{ color: "var(--dn)" }}>▼ {b.down} down</span><span>{b.n - b.up - b.down} neutral</span><span>score {b.score?.toFixed(2) ?? "–"}</span></div>}
          <div className="note" style={{ marginTop: 6 }}>How many of our indicators point the same way. None has a demonstrated edge, so a green needle is a reason to look, not a reason to buy. Buy zone from +0.35, avoid zone from −0.35.</div>
        </Card>
        <Card title="Trader's call">
          {!idea ? <div className="note">{plan ? "Not discussed in the latest plan: it passed on this instrument." : "No plan yet."}</div> : (
            <div className="grid" style={{ gap: 6 }}>
              <div className="row"><Pill tone={idea.action === "open_long" ? "up" : idea.action === "wait" ? "warn" : "dn"}>{idea.action.replace("_", " ")}</Pill><span className="note">conviction</span><span className="bar" style={{ width: 70 }}><i style={{ width: `${Math.round(idea.conviction * 100)}%` }} /></span><span className="num mu">{idea.conviction.toFixed(2)}</span></div>
              <div className="note">{idea.thesis}</div>
              {idea.action === "wait" && <div className="note"><b>Wrong if / re-look:</b> {idea.invalidation}</div>}
              {idea.gate_whatif && <div className="note">{idea.gate_whatif.approved ? <span className="up">Gate would approve {idea.gate_whatif.qty} units (${idea.gate_whatif.notional?.toFixed(2)}), ${idea.gate_whatif.risk_amount?.toFixed(2)} at risk.</span> : <span className="dn">Gate would refuse: {idea.gate_whatif.reasons?.join("; ")}</span>}</div>}
              {idea.action === "open_long" && idea.tradable && !idea.outcome && <ActionButton className="btn sm primary" label="Propose to gate" run={() => post(`/api/ideas/${idea.insight_id}/propose`)} onDone={onProposed} />}
            </div>
          )}
        </Card>
        <Card title="Wait until"><Triggers triggers={triggers} prices={prices} only={symbol} /></Card>
      </div>
    </div>
  );
}

export default function Trader() {
  const plans = useApi("/api/trader/plans?limit=10", 20000);
  const sig = useApi("/api/signals", 60000);
  const [sel, setSel] = useState(0);
  const [packet, setPacket] = useState<Json | null>(null);
  const [proposed, setProposed] = useState<Json | null>(null);
  const [focusSym, setFocusSym] = useState<string | null>(null);
  if (!plans.data) return <Loading error={plans.error} />;
  const list: Json[] = plans.data.plans, plan = list[sel], latest = list[0], card = plans.data.card;
  const rows: Json[] = (sig.data?.rows ?? []).filter((r: Json) => r.available);
  const prices: Record<string, number> = Object.fromEntries(rows.filter((r) => r.price).map((r) => [r.symbol, r.price]));
  const focus = focusSym ?? (rows.find((r) => r.symbol === "BTCUSDT") ?? rows[0])?.symbol ?? null;
  const ideaBySym: Record<string, Json> = Object.fromEntries((latest?.ideas ?? []).map((i: Json) => [i.instrument, i]));
  const triggers: Json[] = latest?.triggers ?? [];

  return (
    <>
      <RunPanel onFinished={() => { plans.reload(); sig.reload(); setSel(0); }} />
      {proposed && (
        <div className={`banner ${proposed.verdict.approved ? "warn" : "dn"}`}>
          {proposed.verdict.approved ? <><b>Proposal created.</b><span>{proposed.verdict.qty} units, gate approved. It expires in 15 minutes.</span><button className="btn sm primary" onClick={() => go("orders")}>Review and approve</button></> : <><b>The gate refused it:</b><span>{proposed.verdict.reasons.join("; ")}</span></>}
          <span className="sp" /><button className="btn sm" onClick={() => setProposed(null)}>Dismiss</button>
        </div>
      )}
      <Hero plan={latest} rows={rows} prices={prices} onFocus={setFocusSym} />
      {sig.data ? (rows.length > 0 && <MeterGrid rows={rows} focus={focus} onFocus={setFocusSym} ideaBySym={ideaBySym} />) : <Loading error={sig.error} />}
      {focus && <Focus symbol={focus} row={rows.find((r) => r.symbol === focus)} plan={latest} triggers={triggers} prices={prices} onProposed={setProposed} />}

      {!plan ? <Card><Empty>No plans yet. Run the trader above.</Empty></Card> : (
        <div className="grid g21">
          <div className="grid">
            <Card title={<>Written plan · {fmt.time(plan.as_of)}</>} right={<span className="note">{fmt.ago(plan.as_of)} · ${plan.cost_usd?.toFixed(3)}</span>}>
              <div className="row" style={{ marginBottom: 8 }}>
                <Pill tone={plan.regime === "stressed" ? "dn" : plan.regime.startsWith("trending") ? "ac" : ""}>{plan.regime}</Pill>
                <Pill>{plan.stance.risk_posture}</Pill><span className="note">cash target {fmt.pct(plan.stance.cash_target_fraction, 0)}</span>
              </div>
              <div className="banner" style={{ marginBottom: 8 }}><b>Edge check</b><span>{plan.edge_check}</span></div>
              <details><summary>Read the full reasoning</summary>
                <p style={{ margin: "8px 0 10px" }}>{plan.narrative}</p>
                <div className="note" style={{ marginBottom: 4 }}><b>What it looked at and passed on.</b></div>
                <p style={{ margin: "0 0 4px" }}>{plan.universe_view}</p>
              </details>
            </Card>
            {plan.ideas.length > 0 && (
              <Card title={`Ideas (${plan.ideas.length})`}>
                <div className="grid" style={{ gap: 10 }}>{plan.ideas.map((i: Json) => <Idea key={i.insight_id} it={i} onProposed={setProposed} />)}</div>
                {plan.dropped?.length > 0 && <div className="note" style={{ marginTop: 10 }}>Corrected by validation: {plan.dropped.join(" · ")}</div>}
              </Card>
            )}
            <div className="grid g2">
              <Card title="Main risks"><ul className="tight">{plan.main_risks.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></Card>
              <Card title="Watchlist"><ul className="tight">{plan.watchlist.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></Card>
            </div>
            <Card title="Triggers in this plan"><Triggers triggers={plan.triggers ?? []} prices={prices} /></Card>
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
