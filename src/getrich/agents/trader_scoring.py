"""Score the trader agent's ideas the only honest way: forward, in shadow, as the trades they describe.

Why no historical backtest of an LLM trader: the model has read the history it would be tested on, so a backtest would measure memory, not
judgement. Instead every `open_long` / `open_short` idea is stored in the hash-chained insight ledger with its exact inputs (the desk packet),
and is resolved later against the hourly bars that came AFTER it. Rules, fixed in advance (they mirror the replay engine):

  entry   at the close of the last closed hourly bar when the idea was issued, plus the cost model's slippage and fee
  stop    stop_pct away from that price; take profit target_pct away (when given); timeout after max_hold_hours bars
  a bar that touches both stop and take profit counts as the stop; a gap through the stop fills at the worse open
  result  net return after fees and slippage on both sides, and R = net return / stop distance

An idea resolves when a stop, target or the timeout is reached on closed bars; until then it is pending. `hold`, `reduce`, `exit` and `wait`
decisions are stored but not scored (there is no counterfactual we can score honestly). Small samples prove nothing: counts sit beside every rate.
"""

from __future__ import annotations

import json
import math
from datetime import timezone

import numpy as np
import pandas as pd

from ..eval.costs import CostModel
from ..eval.data import load_bars
from ..eval.labels import EPS
from ..obs.events import emit, utcnow
from ..store.db import connect
from ..trading import instruments

SERVICE = "agents.trader_scoring"
LEGACY = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}      # the first plans named assets this way
SCORED = ("open_long", "open_short")


def simulate(idea: dict, bars: pd.DataFrame, costs: CostModel | None = None) -> dict | None:
    """Resolve one idea against closed hourly bars after its issue bar. Returns None while it is still open."""
    costs = costs or CostModel()
    slip, fee = costs.slippage_bps / 1e4, costs.fee_bps / 1e4
    sign = 1 if idea["action"] == "open_long" else -1
    px = float(idea["price_at_issue"])
    entry = px * (1 + sign * slip)
    stop = px * (1 - sign * idea["stop_pct"])
    tp = px * (1 + sign * idea["target_pct"]) if idea.get("target_pct") else None
    issued = pd.Timestamp(idea["issue_bar_open"])
    issued = issued.tz_localize("UTC") if issued.tzinfo is None else issued.tz_convert("UTC")      # stored as UTC text
    after = bars[bars.index > issued]
    horizon = int(idea["max_hold_hours"])
    for i, (ts, row) in enumerate(after.iterrows(), start=1):
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        kind = ref = None
        if sign > 0:
            if l <= stop * (1 + EPS):
                kind, ref = "stop", min(stop, o)
            elif tp is not None and h >= tp * (1 - EPS):
                kind, ref = "take_profit", o if o >= tp else tp
        else:
            if h >= stop * (1 - EPS):
                kind, ref = "stop", max(stop, o)
            elif tp is not None and l <= tp * (1 + EPS):
                kind, ref = "take_profit", o if o <= tp else tp
        if kind is None and i >= horizon:
            kind, ref = "timeout", c
        if kind:
            exit_fill = ref * (1 - sign * slip)
            gross = sign * (exit_fill / entry - 1)
            net = gross - 2 * fee
            return {"kind": kind, "bars": i, "gross": gross, "net": net, "r": net / idea["stop_pct"], "exit_ts": f"{ts:%Y-%m-%d %H:%M}"}
    return None


def symbol_of(asset: str, payload: dict) -> str:
    return payload.get("instrument") or LEGACY.get(asset, asset)


def score_ideas(now=None) -> dict:
    """Resolve pending trade ideas. Bars are loaded with no database lock held; outcomes are written afterwards."""
    now = now or utcnow()
    with connect() as con:
        rows = con.execute(
            "SELECT i.insight_id, i.asset, i.payload FROM insights i LEFT JOIN insight_outcomes o ON o.insight_id = i.insight_id "
            "WHERE o.insight_id IS NULL AND json_extract_string(i.payload, '$.kind') = 'trade_idea' ORDER BY i.seq").fetchall()
    out = {"resolved": 0, "pending": 0}
    bars: dict[str, pd.DataFrame] = {}
    resolved = []
    for insight_id, asset, payload in rows:
        p = json.loads(payload)
        sym = symbol_of(asset, p)
        if p.get("action") not in SCORED or instruments.get(sym) is None:
            continue
        if sym not in bars:
            bars[sym] = load_bars(sym, "1h", venue=instruments.bar_venue(sym))
        res = simulate(p, bars[sym], instruments.cost_for(sym))
        if res is None:
            out["pending"] += 1
            continue
        resolved.append((insight_id, now, max(1, math.ceil(int(p["max_hold_hours"]) / 24)), res["net"], bool(res["net"] > 0),
                         json.dumps({"r": res["r"], "kind": res["kind"], "bars": res["bars"], "gross": res["gross"], "setup": p.get("setup"), "action": p["action"], "exit": res["exit_ts"]})))
        out["resolved"] += 1
    if resolved:
        with connect() as con:
            con.executemany("INSERT INTO insight_outcomes VALUES (?,?,?,?,?,?)", resolved)
    emit("agents.trader_score_run", service=SERVICE, **out)
    return out


def _stats(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0}
    a = np.array(rs)
    return {"n": len(a), "win_rate": round(float((a > 0).mean()), 2), "avg_r": round(float(a.mean()), 2), "total_r": round(float(a.sum()), 2)}


def _rows(con, limit: int | None = None):
    q = ("SELECT i.as_of, i.asset, i.payload, o.detail, o.realized_return FROM insights i LEFT JOIN insight_outcomes o ON o.insight_id = i.insight_id "
         "WHERE json_extract_string(i.payload, '$.kind') = 'trade_idea' ORDER BY i.seq DESC" + (f" LIMIT {int(limit)}" if limit else ""))
    return con.execute(q).fetchall()


def scorecard(con) -> dict:
    rows = _rows(con)
    scored = [(json.loads(p), json.loads(d) if d else None) for _a, _asset, p, d, _r in rows if json.loads(p).get("action") in SCORED]
    done = [(p, d) for p, d in scored if d]
    by_setup, by_conv = {}, {"low (<0.4)": [], "mid (0.4-0.6)": [], "high (>0.6)": []}
    for p, d in done:
        by_setup.setdefault(p.get("setup", "other"), []).append(d["r"])
        c = p.get("conviction", 0)
        by_conv["low (<0.4)" if c < 0.4 else "mid (0.4-0.6)" if c <= 0.6 else "high (>0.6)"].append(d["r"])
    actions = {}
    for _a, _asset, p, _d, _r in rows:
        a = json.loads(p).get("action", "?")
        actions[a] = actions.get(a, 0) + 1
    return {"decisions": len(rows), "by_action": actions, "ideas_scored": len(scored), "resolved": _stats([d["r"] for _p, d in done]), "pending": len(scored) - len(done),
            "by_setup": {k: _stats(v) for k, v in by_setup.items()}, "by_conviction": {k: _stats(v) for k, v in by_conv.items()},
            "stops": sum(1 for _p, d in done if d["kind"] == "stop"), "targets": sum(1 for _p, d in done if d["kind"] == "take_profit"), "timeouts": sum(1 for _p, d in done if d["kind"] == "timeout")}


def journal(n: int = 8) -> dict:
    """What the trader sees about its own recent calls: the last n decisions with outcomes, and the running record."""
    with connect() as con:
        rows = _rows(con, n)
        card = scorecard(con)
    recent = []
    for as_of, asset, p, d, _ret in rows:
        p, d = json.loads(p), (json.loads(d) if d else None)
        item = {"issued": f"{as_of.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC", "instrument": symbol_of(asset, p), "action": p.get("action"), "setup": p.get("setup"), "conviction": p.get("conviction"), "thesis": (p.get("thesis") or "")[:160]}
        if p.get("action") in SCORED:
            item["outcome"] = {"r": round(d["r"], 2), "exit": d["kind"], "hours": d["bars"]} if d else "pending"
        recent.append(item)
    return {"recent_decisions": recent, "record": card}
