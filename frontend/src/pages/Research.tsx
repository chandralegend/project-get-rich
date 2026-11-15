import { useEffect, useMemo, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { get, useApi, Json } from "../api";
import { go } from "../App";
import { Card, Empty, fmt, Loading, Pill } from "../ui";

function verdictTone(v: string | null): "" | "up" | "dn" | "warn" {
  if (!v) return "";
  const t = v.toUpperCase();
  if (t.includes("NOT SHOWN") || t.includes("NO EDGE")) return "dn";
  if (t.includes("SHOWS VALUE")) return "up";
  return "warn";
}

function Doc({ dir, name }: { dir: string; name: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setHtml(null); setErr(null);
    fetch(`/api/docs/${dir}/${name}`).then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status))))).then(async (t) => setHtml(DOMPurify.sanitize(await marked.parse(t)))).catch((e) => setErr(String(e.message)));
  }, [dir, name]);
  if (err) return <Loading error={err} />;
  if (html == null) return <Loading />;
  return <div className="prose" dangerouslySetInnerHTML={{ __html: html }} />;
}

export default function Research({ arg }: { arg: string }) {
  const r = useApi("/api/research", 0);
  const [filter, setFilter] = useState<"results" | "prereg" | "all">("results");
  const [q, setQ] = useState("");
  const docs: Json[] = useMemo(() => (r.data?.docs ?? []).filter((d: Json) => (filter === "all" || (filter === "prereg") === (d.kind === "preregistration")) && (d.title + d.name).toLowerCase().includes(q.toLowerCase())).sort((a: Json, b: Json) => b.modified - a.modified), [r.data, filter, q]);
  if (!r.data) return <Loading error={r.error} />;
  const [dir, name] = arg.includes("~") ? arg.split("~") : ["", ""];

  return (
    <div className="grid g12">
      <Card title="Studies" right={<span className="note">{r.data.trials.count} trials counted for Deflated Sharpe</span>}>
        <div className="row" style={{ marginBottom: 8 }}>
          {([["results", "Results"], ["prereg", "Pre-registrations"], ["all", "All"]] as const).map(([k, l]) => <button key={k} className={`chip ${filter === k ? "on" : ""}`} style={{ padding: "1px 10px" }} onClick={() => setFilter(k)}>{l}</button>)}
        </div>
        <input placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "100%", padding: "6px 10px", borderRadius: 8, border: "1px solid var(--line2)", background: "var(--s2)", color: "var(--tx)", marginBottom: 8 }} />
        <div style={{ maxHeight: "70vh", overflowY: "auto" }}>
          {docs.map((d) => (
            <div key={d.dir + d.name} onClick={() => go("research", `${d.dir}~${d.name}`)} style={{ padding: "7px 8px", borderRadius: 8, cursor: "pointer", background: dir === d.dir && name === d.name ? "var(--s2)" : undefined }}>
              <div>{d.title}</div>
              <div className="row" style={{ gap: 6 }}>{d.verdict && <Pill tone={verdictTone(d.verdict)}>{d.verdict.length > 46 ? d.verdict.slice(0, 46) + "…" : d.verdict}</Pill>}<span className="note">{d.dir}/{d.name}</span></div>
            </div>
          ))}
          {docs.length === 0 && <Empty>No documents match.</Empty>}
        </div>
      </Card>
      <Card title={name || "Reading"}>
        {name ? <Doc dir={dir} name={name} /> : <Empty>Pick a study on the left. Every strategy and model we tried is here, with its pre-registered bar and what it did. So far nothing has cleared the bar.</Empty>}
      </Card>
    </div>
  );
}
