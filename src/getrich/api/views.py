"""Read models for the web UI: plain functions that return JSON-ready dicts from the store, the event log and the docs folder.

Nothing here decides or trades. Slow views are cached for a short time because the UI polls. Every database read is one short `connect()` block (the lock
is not re-entrant) and bars are loaded with no lock held.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from datetime import timedelta
from pathlib import Path

from .. import config
from ..agents import briefing, desk, trader_scoring
from ..llm import budget
from ..obs.events import iso, parse_ts, utcnow
from ..obs.heartbeat import read as read_heartbeat
from ..ops import scheduler, watchdog
from ..store.db import connect
from ..store.ledger import count_insights, verify_chain
from ..trading import book, instruments, limits as L

_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def cached(key: str, ttl: float, fn):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def root_dir() -> Path:
    return config.root()


# ------------------------------------------------------------------------------------------------ desk

def overview() -> dict:
    now = utcnow()
    port = desk._portfolio_view(now)
    with connect() as con:
        curve = con.execute("SELECT ts, equity FROM equity_snapshots WHERE venue = 'paper' ORDER BY ts DESC LIMIT 600").fetchall()
        spent = budget.month_spend_con(con)
    summary = book.realized_summary()
    plans = trader_plans(1)
    alerts = active_alerts()
    return {
        "as_of": iso(now), "portfolio": port, "equity_curve": [{"t": iso(t), "equity": e} for t, e in reversed(curve)], "realized": summary,
        "budget": {"spent": round(spent, 4), "cap": budget.monthly_cap()}, "alerts": alerts, "last_plan": plans["plans"][0] if plans["plans"] else None,
        "start_equity": book.start_equity(),
    }


def active_alerts() -> list[dict]:
    try:
        state = json.loads((config.state_dir() / "alerts.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk in ("severity", "message", "action", "since", "first_seen")}} for k, v in state.get("active", {}).items()]


# ------------------------------------------------------------------------------------------------ markets

def universe(classes: tuple[str, ...] | None = None) -> dict:
    def build():
        scan, missing, _d, _h = desk.scan_universe(utcnow(), classes)
        rows = [{"symbol": s, **r} for s, r in scan.items()]
        return {"as_of": iso(utcnow()), "rows": rows, "no_data_yet": missing}
    return cached(f"universe:{classes}", 90, build)


def bars(symbol: str, timeframe: str = "1h", limit: int = 500) -> dict:
    inst = instruments.get(symbol)
    if inst is None:
        raise KeyError(symbol)
    if timeframe not in ("1h", "1d"):
        raise ValueError("timeframe must be 1h or 1d")
    limit = max(10, min(int(limit), 3000))
    with connect() as con:
        rows = con.execute("SELECT ts_open, open, high, low, close, volume FROM bars WHERE venue = ? AND symbol = ? AND timeframe = ? ORDER BY ts_open DESC LIMIT ?",
                           [inst.source, symbol, timeframe, limit]).fetchall()
    return {"symbol": symbol, "name": inst.name, "class": inst.asset_class, "timeframe": timeframe,
            "bars": [{"t": int(t.timestamp()), "o": o, "h": h, "l": l, "c": c, "v": v} for t, o, h, l, c, v in reversed(rows)]}


def instrument_detail(symbol: str) -> dict:
    """Full daily and hourly view for one instrument, the same view the trader gets for the instruments it studies closely."""
    inst = instruments.get(symbol)
    if inst is None:
        raise KeyError(symbol)
    now = utcnow()
    d, h = desk._bars(symbol, "1d"), desk._bars(symbol, "1h")
    out = {"symbol": symbol, "name": inst.name, "class": inst.asset_class, "note": inst.note, "daily": desk._daily_view(d, inst.asset_class), "hourly": desk._hourly_view(h, now, inst.asset_class),
           "market_open": instruments.is_open(symbol, now), "round_trip_cost_pct": round(inst.cost.round_trip() * 100, 3)}
    if inst.asset_class == "crypto":
        out["forecasts"] = desk._forecast_view(symbol, d)
        if symbol in ("BTCUSDT", "ETHUSDT"):
            out["pinet"] = desk._pinet_view(symbol)
    return out


def pinet() -> dict:
    """The forward PI-Net study as the screens show it: today's call per coin, the running record and how far the pre-registered checkpoint is."""
    def build():
        from ..eval import pinet_live

        recs = pinet_live.records()
        v = pinet_live.verdict(recs)
        return {"latest": pinet_live.latest(), "summary": v["summary"], "p": v["p"], "due": v["due"], "days_since_first": v["days_since_first"], "left": v["left"], "checks": v["checks"],
                "shows_value": v["shows_value"], "criteria": {"min_delta_r": pinet_live.MIN_DELTA, "alpha": pinet_live.ALPHA, "min_take": pinet_live.MIN_TAKE, "check_days": pinet_live.CHECK_DAYS,
                                                               "check_resolved": pinet_live.CHECK_RESOLVED}}
    return cached("pinet", 60, build)


# ------------------------------------------------------------------------------------------------ trader

def trader_plans(limit: int = 8) -> dict:
    with connect() as con:
        plans = con.execute("SELECT insight_id, as_of, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'trader_plan' ORDER BY seq DESC LIMIT ?", [limit]).fetchall()
        ids = [json.loads(p)["plan_id"] for _i, _a, p in plans]
        ideas = []
        if ids:
            q = ",".join("?" * len(ids))
            ideas = con.execute(
                "SELECT i.insight_id, i.as_of, i.asset, i.payload, o.detail, o.realized_return FROM insights i LEFT JOIN insight_outcomes o ON o.insight_id = i.insight_id "
                f"WHERE json_extract_string(i.payload, '$.kind') = 'trade_idea' AND json_extract_string(i.payload, '$.plan_id') IN ({q}) ORDER BY i.seq", ids).fetchall()
        card = trader_scoring.scorecard(con)
    by_plan: dict[str, list] = {}
    for iid, as_of, asset, payload, detail, ret in ideas:
        p = json.loads(payload)
        by_plan.setdefault(p["plan_id"], []).append({
            "insight_id": iid, "issued": iso(as_of), "instrument": trader_scoring.symbol_of(asset, p), **{k: p.get(k) for k in (
                "action", "setup", "conviction", "thesis", "invalidation", "stop_pct", "target_pct", "max_hold_hours", "risk_fraction", "price_at_issue", "tradable", "gate_whatif")},
            "outcome": ({**json.loads(detail), "net_return": ret} if detail else (None if p.get("action") in trader_scoring.SCORED else "not scored"))})
    out = []
    for iid, as_of, payload in plans:
        p = json.loads(payload)
        out.append({"insight_id": iid, "as_of": iso(as_of), "plan_id": p["plan_id"], "regime": p["regime"], "narrative": p["narrative"], "main_risks": p["main_risks"], "edge_check": p["edge_check"],
                    "stance": p["stance"], "universe_view": p.get("universe_view"), "watchlist": p["watchlist"], "review_of_past_calls": p["review_of_past_calls"], "dropped": p.get("dropped", []),
                    "cost_usd": p.get("cost_usd"), "packet_ref": p.get("packet_ref"), "ideas": by_plan.get(p["plan_id"], [])})
    return {"plans": out, "card": card}


def packet(ref: str) -> dict:
    with connect() as con:
        row = con.execute("SELECT summary, ingested_at FROM news_items WHERE item_id = ? AND source = 'desk_packet'", [ref]).fetchone()
    if not row:
        raise KeyError(ref)
    return {"ref": ref, "ingested_at": iso(row[1]), "packet": json.loads(row[0])}


def idea(insight_id: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT as_of, asset, payload FROM insights WHERE insight_id = ? AND json_extract_string(payload, '$.kind') = 'trade_idea'", [insight_id]).fetchone()
    if not row:
        return None
    p = json.loads(row[2])
    return {"as_of": row[0], "instrument": trader_scoring.symbol_of(row[1], p), **p}


# ------------------------------------------------------------------------------------------------ orders and risk

def orders(limit: int = 40) -> dict:
    rows = book.list_orders(limit, "paper")
    state = book.load_state(instruments.symbols(), utcnow())
    lim, why = L.load()
    return {"orders": [{**o, "created_at": iso(o["created_at"])} for o in rows], "positions": desk._portfolio_view(utcnow())["positions"], "halted": state.halt_latched, "killed": state.killed,
            "limits": ({"profile": lim.profile, "max_exposure_fraction": lim.max_exposure_fraction, "account_drawdown_halt": lim.account_drawdown_halt, "daily_loss_halt": lim.daily_loss_halt,
                        "risk_per_trade": lim.risk_per_trade, "max_leverage": lim.max_leverage, "allow_short": lim.allow_short, "pinned": True} if lim else {"pinned": False, "why": why}),
            "equity": state.equity, "peak_equity": state.peak_equity}


# ------------------------------------------------------------------------------------------------ news

def news() -> dict:
    now = utcnow()
    with connect() as con:
        events, withheld = briefing.gather_events(con, 72)
        flags = con.execute("SELECT as_of, asset, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'risk_flag' AND epoch(as_of) >= ? ORDER BY seq DESC LIMIT 20",
                            [(now - timedelta(hours=72)).timestamp()]).fetchall()
        brief = con.execute("SELECT as_of, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'briefing' ORDER BY seq DESC LIMIT 1").fetchone()
    out = {"events": desk._with_ages(events, now), "withheld": withheld, "freshness": desk.news_freshness(now), "flags": [{"as_of": iso(a), "asset": asset, **json.loads(p)} for a, asset, p in flags]}
    if brief:
        out["briefing"] = {"as_of": iso(brief[0]), **json.loads(brief[1])}
    return out


# ------------------------------------------------------------------------------------------------ system

def forecast_status() -> list[dict]:
    from ..forecast import live

    try:
        return live.status()
    except Exception:
        return []


def health() -> dict:
    def build():
        services = {}
        for svc, max_age in {**watchdog.EXPECTED_MAX_AGE, "watchdog": 180}.items():
            hb = read_heartbeat(svc)
            last = hb.get("last_ok_ts") if hb else None
            age = (utcnow() - parse_ts(last)).total_seconds() if last else None
            services[svc] = {"last_ok": last, "age_s": age, "max_age_s": max_age, "state": "never" if hb is None else ("ok" if age is not None and age <= max_age else "stale")}
        with connect() as con:
            fresh = con.execute("SELECT venue, symbol, timeframe, count(*), max(ts_open) FROM bars GROUP BY 1, 2, 3 ORDER BY 2, 3").fetchall()
            chain_ok, n_chain, bad = verify_chain(con)
            n_insights = count_insights(con)
            spent = budget.month_spend_con(con)
        now = utcnow()
        data = []
        for venue, sym, tf, n, last in fresh:
            data.append({"venue": venue, "symbol": sym, "timeframe": tf, "bars": n, "last": iso(last), "age_hours": round((now - last).total_seconds() / 3600, 1), "class": (instruments.get(sym).asset_class if instruments.get(sym) else "other")})
        free = shutil.disk_usage(config.data_dir()).free / 2**30
        db = config.db_path()
        return {"as_of": iso(now), "services": services, "scheduler": scheduler.read_all(), "forecasts": forecast_status(), "data": data, "ledger": {"ok": chain_ok, "insights": n_insights, "bad_seq": bad},
                "budget": {"spent": round(spent, 4), "cap": budget.monthly_cap()}, "alerts": active_alerts(), "disk_free_gib": round(free, 1), "db_mb": round(db.stat().st_size / 2**20, 1) if db.exists() else 0,
                "trader_classes": list(desk.trader_classes()), "in_docker": os.path.exists("/.dockerenv")}
    return cached("health", 20, build)


# ------------------------------------------------------------------------------------------------ research

DOC_DIRS = ("docs", "research")
_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.md$")
_VERDICT = re.compile(r"(NOT SHOWN|SHOWS VALUE|PASS\b|FAIL\b|not shown|shown)", re.I)


def research() -> dict:
    items = []
    for d in DOC_DIRS:
        for p in sorted((root_dir() / d).glob("*.md")):
            text = p.read_text(errors="replace")
            title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("# ")), p.stem)
            verdict = None
            for ln in text.splitlines():
                if ln.startswith("**Verdict") or ln.lower().startswith("verdict") or "Verdict:" in ln:
                    verdict = ln.strip("* ")[:200]
                    break
            items.append({"dir": d, "name": p.name, "title": title, "modified": p.stat().st_mtime, "verdict": verdict, "kind": "preregistration" if p.name.startswith("preregistration") else "result"})
    trials = []
    tp = root_dir() / "docs" / "trials.json"
    if tp.exists():
        trials = json.loads(tp.read_text())
    return {"docs": items, "trials": {"count": len(trials), "entries": trials}}


def doc(directory: str, name: str) -> str:
    if directory not in DOC_DIRS or not _NAME.match(name):
        raise KeyError(name)
    p = root_dir() / directory / name
    if not p.is_file():
        raise KeyError(name)
    return p.read_text(errors="replace")
