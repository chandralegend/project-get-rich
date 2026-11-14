"""`getrich status`: the terminal status screen, derived from the event log and the store."""

from __future__ import annotations

import json
import shutil

from rich.console import Console
from rich.table import Table

from .. import config
from ..store.db import connect
from ..ops.watchdog import EXPECTED_MAX_AGE
from .events import parse_ts, utcnow
from .heartbeat import read
from .ingest import ingest_events

NOT_BUILT = {
    "AGENTS": "not built yet (Phase 3)",
    "MODEL": "not built yet (Phase 2)",
    "RISK": "not built yet (Phase 4)",
    "ORDERS": "not built yet (Phase 4)",
}


def _age(ts: str | None) -> tuple[str, float | None]:
    if not ts:
        return "never", None
    secs = (utcnow() - parse_ts(ts)).total_seconds()
    if secs >= 86400:
        return f"{secs / 86400:.1f}d ago", secs
    if secs >= 3600:
        return f"{secs / 3600:.1f}h ago", secs
    return f"{max(secs, 0) / 60:.0f}m ago", secs


def build_lines() -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []

    health = []
    for svc, max_age in {**EXPECTED_MAX_AGE, "watchdog": 180}.items():
        hb = read(svc)
        age_txt, secs = _age(hb.get("last_ok_ts") if hb else None)
        state = "[green]OK[/]" if secs is not None and secs <= max_age else ("[yellow]never[/]" if hb is None else "[red]STALE[/]")
        health.append(f"{svc} {state} ({age_txt})")
    lines.append(("HEALTH", " · ".join(health)))

    with connect() as con:
        ingest_events(con)
        bars = con.execute(
            "SELECT symbol, timeframe, count(*), max(ts_open) FROM bars GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
        news_24h = con.execute(
            "SELECT source, count(*) FROM news_items WHERE ingested_at > now() - INTERVAL 1 DAY GROUP BY 1 ORDER BY 1"
        ).fetchall()
        news_total = con.execute("SELECT count(*) FROM news_items").fetchone()[0]
        events_total = con.execute("SELECT count(*) FROM events").fetchone()[0]
        alerts_24h = con.execute(
            "SELECT json_extract_string(data, '$.severity'), count(*) FROM events "
            "WHERE event = 'alert.raised' AND ts > now() - INTERVAL 1 DAY GROUP BY 1"
        ).fetchall()

    if bars:
        parts = [f"{s} {tf}: {n} bars, latest {latest:%Y-%m-%d}" for s, tf, n, latest in bars]
        lines.append(("DATA", " · ".join(parts)))
    else:
        lines.append(("DATA", "no bars yet: run `getrich collect-binance`"))
    if news_24h:
        lines.append(("NEWS", f"{sum(n for _, n in news_24h)} new in 24h ({', '.join(f'{s} {n}' for s, n in news_24h)}) · {news_total} total"))
    else:
        lines.append(("NEWS", f"0 new in 24h · {news_total} total"))

    for key, text in NOT_BUILT.items():
        lines.append((key, f"[dim]{text}[/]"))

    free = shutil.disk_usage(config.data_dir()).free / 2**30
    disk_style = "red" if free < 5 else "yellow" if free < 10 else "green"
    lines.append(("SYSTEM", f"disk free [{disk_style}]{free:.1f} GiB[/] · event log rows {events_total}"))

    try:
        active = json.loads((config.state_dir() / "alerts.json").read_text()).get("active", {})
    except (OSError, json.JSONDecodeError):
        active = {}
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for a in active.values():
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
    raised = " ".join(f"{sev}:{n}" for sev, n in alerts_24h) or "none"
    lines.append(("ALERTS", f"active P0 {counts['P0']} · P1 {counts['P1']} · P2 {counts['P2']} · raised in 24h: {raised}"))
    for key, a in active.items():
        if a["severity"] in ("P0", "P1"):
            lines.append(("", f"[red]{a['severity']}[/] {a['message']}"))
    return lines


def render(console: Console | None = None) -> None:
    console = console or Console()
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(overflow="fold")
    for key, text in build_lines():
        table.add_row(key, text)
    console.print(f"[bold]getrich status[/]  {utcnow():%Y-%m-%d %H:%M} UTC")
    console.rule(style="dim")
    console.print(table)
