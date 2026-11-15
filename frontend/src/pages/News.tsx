import { useApi, Json } from "../api";
import { Card, Empty, fmt, Loading, Pill } from "../ui";

const dirTone = (d: string) => (d === "risk_on" ? "up" : d === "risk_off" ? "dn" : "") as "" | "up" | "dn";
const sev = (s: string) => (s === "high" ? "dn" : s === "medium" ? "warn" : "") as "" | "dn" | "warn";

export default function News() {
  const n = useApi("/api/news", 60000);
  if (!n.data) return <Loading error={n.error} />;
  const b = n.data.briefing;
  return (
    <>
      <div className="grid g21">
        <Card title="Latest briefing" right={b && <span className="note">{fmt.ago(b.as_of)}</span>}>
          {!b ? <Empty>No briefing yet. It is written daily at 06:00.</Empty> : (
            <div className="grid" style={{ gap: 8 }}>
              <div className="row"><b style={{ fontSize: 15 }}>{b.headline}</b><Pill tone={b.regime === "stressed" ? "dn" : ""}>{b.regime}</Pill></div>
              <p style={{ margin: 0 }}>{b.summary}</p>
              {b.watch_next?.length > 0 && <div><div className="note"><b>Watch next</b></div><ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{b.watch_next.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul></div>}
            </div>
          )}
        </Card>
        <Card title="Risk flags (72h)">
          {n.data.flags.length === 0 ? <Empty>None.</Empty> : n.data.flags.map((f: Json, i: number) => (
            <div key={i} style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
              <div className="row"><Pill tone={sev(f.severity)}>{f.severity}</Pill><b>{f.asset}</b><span className="mu">{f.flag}</span><span className="sp" /><span className="note">{fmt.ago(f.as_of)}</span></div>
              <div className="note">{f.reason}</div>
            </div>
          ))}
        </Card>
      </div>
      <Card title={`Classified events (${n.data.events.length})`} right={<span className="note">{n.data.withheld} withheld as suspicious · summaries written by a model from untrusted text</span>}>
        {n.data.events.length === 0 ? <Empty>No usable events in the last 72 hours.</Empty> : n.data.events.map((e: Json) => (
          <div key={e.ref} style={{ padding: "7px 0", borderBottom: "1px solid var(--line)" }}>
            <div className="row"><Pill tone={dirTone(e.direction)}>{e.direction.replace("_", " ")}</Pill><Pill tone={sev(e.magnitude)}>{e.magnitude}</Pill><span className="mu">{e.event_type.replace(/_/g, " ")}</span><span className="note">{e.assets.join(", ")}</span><span className="sp" /><span className="note">{e.source}</span></div>
            <div>{e.summary}</div>
          </div>
        ))}
      </Card>
    </>
  );
}
