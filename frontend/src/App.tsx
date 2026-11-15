import { useEffect, useState } from "react";
import { useApi } from "./api";
import { fmt, Pill } from "./ui";
import Desk from "./pages/Desk";
import Trader from "./pages/Trader";
import Markets from "./pages/Markets";
import Orders from "./pages/Orders";
import News from "./pages/News";
import Research from "./pages/Research";
import System from "./pages/System";

const PAGES = [
  { id: "desk", label: "Desk", icon: "M3 12l4-5 4 3 6-7" },
  { id: "trader", label: "Trader", icon: "M12 3a5 5 0 015 5c0 2-1 3-2 4v2H9v-2c-1-1-2-2-2-4a5 5 0 015-5zM9 18h6M10 21h4" },
  { id: "markets", label: "Markets", icon: "M4 20V10M10 20V4M16 20v-8M22 20H2" },
  { id: "orders", label: "Orders & risk", icon: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" },
  { id: "news", label: "News", icon: "M4 5h16v14H4zM8 9h8M8 13h8M8 16h5" },
  { id: "research", label: "Research", icon: "M9 3h6M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3" },
  { id: "system", label: "System", icon: "M4 6h16M4 12h16M4 18h16M8 4v4M16 10v4M10 16v4" },
] as const;

function parseHash(): { page: string; arg: string } {
  const [, page = "desk", arg = ""] = window.location.hash.replace(/^#/, "").split("/");
  return { page: PAGES.some((p) => p.id === page) ? page : "desk", arg: decodeURIComponent(arg) };
}

export function go(page: string, arg?: string) {
  window.location.hash = `/${page}${arg ? `/${encodeURIComponent(arg)}` : ""}`;
}

export default function App() {
  const [route, setRoute] = useState(parseHash());
  const [theme, setTheme] = useState<string>(() => { try { return localStorage.getItem("theme") || "auto"; } catch { return "auto"; } });
  const ov = useApi("/api/overview", 15000);
  const jobs = useApi("/api/jobs", 6000);

  useEffect(() => { const f = () => setRoute(parseHash()); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  useEffect(() => {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theme", theme); } catch { /* storage may be blocked */ }
  }, [theme]);

  const p = ov.data?.portfolio;
  const pending = (p?.pending_proposals ?? []).length;
  const running = (jobs.data?.jobs ?? []).filter((j: any) => j.status === "running");
  const alerts = ov.data?.alerts ?? [];
  const title = PAGES.find((x) => x.id === route.page)?.label ?? "Desk";

  return (
    <div className="app">
      <nav className="rail" aria-label="Main">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="var(--s2)" /><path d="M6 22 L13 14 L18 18 L26 8" fill="none" stroke="var(--ac)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
          getrich
        </div>
        {PAGES.map((x) => (
          <button key={x.id} className={`nav ${route.page === x.id ? "on" : ""}`} onClick={() => go(x.id)}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={x.icon} /></svg>
            {x.label}
            {x.id === "orders" && (pending > 0 || p?.halted || p?.killed) && <span className="dot" />}
            {x.id === "trader" && running.some((j: any) => j.kind === "trader") && <span className="dot" style={{ background: "var(--ac)" }} />}
          </button>
        ))}
        <div className="foot">
          <div className="row" style={{ gap: 4 }}>
            {["auto", "dark", "light"].map((t) => <button key={t} className={`chip ${theme === t ? "on" : ""}`} style={{ padding: "1px 8px", fontSize: 11 }} onClick={() => setTheme(t)}>{t}</button>)}
          </div>
          <span>Paper account. Nothing here touches an exchange.</span>
        </div>
      </nav>
      <div className="main">
        <header className="top">
          <span className="t">{title}</span>
          <Pill tone="ac">PAPER</Pill>
          {p?.killed && <Pill tone="dn">KILL SWITCH ON</Pill>}
          {p?.halted && <Pill tone="dn">DRAWDOWN HALT</Pill>}
          {pending > 0 && <a href="#/orders"><Pill tone="warn">{pending} proposal{pending > 1 ? "s" : ""} to review</Pill></a>}
          {alerts.length > 0 && <a href="#/system"><Pill tone="warn">{alerts.length} alert{alerts.length > 1 ? "s" : ""}</Pill></a>}
          {running.length > 0 && <Pill tone="ac">running: {running.map((j: any) => j.kind).join(", ")}</Pill>}
          <span className="num" title="account equity">{p ? fmt.usd(p.equity) : "…"}</span>
        </header>
        <div className="page">
          {route.page === "desk" && <Desk ov={ov.data} err={ov.error} />}
          {route.page === "trader" && <Trader />}
          {route.page === "markets" && <Markets symbol={route.arg} />}
          {route.page === "orders" && <Orders />}
          {route.page === "news" && <News />}
          {route.page === "research" && <Research arg={route.arg} />}
          {route.page === "system" && <System />}
        </div>
      </div>
    </div>
  );
}
