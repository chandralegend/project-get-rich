import { useState } from "react";
import { post, useApi, Json } from "../api";
import { ActionButton, Card, Empty, fmt, Kpi, Loading, Pill, Table } from "../ui";

export default function System() {
  const h = useApi("/api/health", 15000);
  const jobs = useApi("/api/jobs", 4000);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useApi(jobId ? `/api/jobs/${jobId}` : null, 2500);
  const [only, setOnly] = useState("all");
  if (!h.data) return <Loading error={h.error} />;
  const d = h.data, sched: Json = d.scheduler?.jobs ?? {};
  const refreshing = (jobs.data?.jobs ?? []).some((j: Json) => j.kind === "refresh-data" && j.status === "running");
  const data: Json[] = d.data.filter((x: Json) => only === "all" || x.class === only);

  return (
    <>
      <div className="kpis">
        <Kpi label="Ledger" value={d.ledger.ok ? "intact" : "BROKEN"} cls={d.ledger.ok ? "up" : "dn"} sub={`${d.ledger.insights} insights, hash-chained`} />
        <Kpi label="Claude this month" value={fmt.usd(d.budget.spent)} sub={`cap ${fmt.usd(d.budget.cap, 0)}`} />
        <Kpi label="Database" value={`${d.db_mb} MB`} sub={`${d.disk_free_gib} GiB disk free`} />
        <Kpi label="Runtime" value={d.in_docker ? "Docker" : "host"} sub={`trader scope: ${d.trader_classes.join(", ")}`} />
      </div>

      {d.alerts.length > 0 && <Card title="Active alerts">{d.alerts.map((a: Json) => <div key={a.key} className="row" style={{ padding: "4px 0" }}><Pill tone={a.severity === "P0" ? "dn" : "warn"}>{a.severity}</Pill><span>{a.message}</span><span className="note">{a.action}</span></div>)}</Card>}

      <div className="grid g2">
        <Card title="Collectors and watchdog">
          <Table head={<><th>Service</th><th>State</th><th className="r">Last success</th></>}>
            {Object.entries(d.services).map(([k, v]: [string, any]) => <tr key={k}><td>{k}</td><td><Pill tone={v.state === "ok" ? "up" : v.state === "never" ? "warn" : "dn"}>{v.state}</Pill></td><td className="r dim">{fmt.ago(v.last_ok)}</td></tr>)}
          </Table>
        </Card>
        <Card title="Scheduled jobs" right={<span className="note">{d.scheduler?.heartbeat ? `scheduler alive ${fmt.ago(d.scheduler.heartbeat)}` : "scheduler not running"}</span>}>
          {Object.keys(sched).filter((k) => !k.startsWith("_")).length === 0 ? <Empty>No scheduler state yet. In Docker the scheduler service writes it.</Empty> : (
            <Table head={<><th>Job</th><th>Last run</th><th className="r">Took</th><th>Result</th></>}>
              {Object.entries(sched).filter(([k]) => !k.startsWith("_")).map(([k, v]: [string, any]) => (
                <tr key={k}><td>{k}</td><td className="dim">{v.running ? "running now" : fmt.ago(v.last_end)}</td><td className="r num dim">{v.seconds != null ? `${v.seconds}s` : "–"}</td><td>{v.running ? <Pill tone="ac">running</Pill> : v.ok == null ? "–" : <Pill tone={v.ok ? "up" : "dn"}>{v.ok ? "ok" : `exit ${v.exit_code}`}</Pill>}</td></tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <Card title="Forecasters" right={<span className="note">{d.scheduler?.models_heartbeat ? `models service alive ${fmt.ago(d.scheduler.models_heartbeat)}` : "models service not running"}</span>}>
        <div className="note" style={{ marginBottom: 8 }}>BTC and ETH only. A separate container (no network, no keys) adds one forecast per model after each daily bar closes. They did not beat a random walk in our tests, so they are shown, not trusted.</div>
        {!(d.forecasts ?? []).length ? <Empty>No forecasts cached.</Empty> : (
          <Table head={<><th>Model</th><th>Symbol</th><th className="r">Newest forecast origin</th><th className="r">Behind the newest daily bar</th></>}>
            {d.forecasts.map((f: Json) => <tr key={f.model + f.symbol}><td>{f.model}</td><td><b>{f.symbol}</b></td><td className="r num dim">{f.newest_origin ?? "none"}</td><td className={`r num ${f.days_behind > 1 ? "warn" : "dim"}`}>{f.error ?? (f.days_behind == null ? "–" : f.days_behind === 0 ? "up to date" : `${f.days_behind} day${f.days_behind === 1 ? "" : "s"}`)}</td></tr>)}
          </Table>
        )}
      </Card>

      <Card title="Market data" right={<span className="row">
        {["all", "crypto", "fx", "metal"].map((c) => <button key={c} className={`chip ${only === c ? "on" : ""}`} style={{ padding: "1px 10px" }} onClick={() => setOnly(c)}>{c}</button>)}
        <ActionButton className="btn sm primary" label={refreshing ? "Refreshing…" : "Refresh now"} disabled={refreshing} run={() => post("/api/data/refresh", { classes: ["crypto", "fx", "metal"] })} onDone={(m) => setJobId(m.id)} />
      </span>}>
        <div className="note" style={{ marginBottom: 8 }}>Crypto from Binance, forex and metals from Yahoo Finance (an unofficial free feed). The scheduler refreshes hourly; forex and metals are naturally stale at the weekend.</div>
        {job.data && <pre className="log" style={{ marginBottom: 8, maxHeight: 140 }}>{job.data.tail || job.data.status}</pre>}
        <Table head={<><th>Symbol</th><th>Source</th><th>Timeframe</th><th className="r">Bars</th><th className="r">Latest bar</th><th className="r">Age</th></>}>
          {data.map((x) => <tr key={x.symbol + x.timeframe}><td><b>{x.symbol}</b></td><td className="dim">{x.venue}</td><td>{x.timeframe}</td><td className="r num">{x.bars.toLocaleString()}</td><td className="r num dim">{x.last.slice(0, 16).replace("T", " ")}</td><td className={`r num ${x.age_hours > (x.timeframe === "1h" ? (x.class === "crypto" ? 3 : 60) : 60) ? "warn" : "dim"}`}>{x.age_hours}h</td></tr>)}
        </Table>
      </Card>
    </>
  );
}
