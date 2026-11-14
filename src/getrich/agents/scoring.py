"""Score shadow views and risk flags against what prices actually did.

This is how the agent layer earns, or fails to earn, any trust. A view is only resolved once its horizon has fully
passed on CLOSED daily bars. Rules, fixed in advance:
  up    hit if the return over the horizon is positive
  down  hit if it is negative
  flat  hit if the absolute return is within one daily-volatility sigma scaled by sqrt(horizon)
A risk flag on BTC or ETH counts as 'followed by a large move' if the absolute return over the next 3 days exceeded
1.5 sigma scaled by sqrt(3). Flags on other assets cannot be scored yet (no bars for them).
Small samples prove nothing: the scorecard always reports the count next to the hit rate.
"""

from __future__ import annotations

import json
import math

import pandas as pd

from ..eval import labels
from ..eval.data import load_bars
from ..obs.events import emit, utcnow
from ..store.db import connect

SERVICE = "agents.scoring"
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
FLAG_HORIZON = 3
FLAG_SIGMAS = 1.5


def _bars(cache: dict, asset: str):
    if asset not in cache:
        daily = load_bars(SYMBOLS[asset], "1d")
        close = daily["close"].copy()
        close.index = close.index + pd.Timedelta(days=1)         # key each close by the moment it became known
        cache[asset] = (close, labels.daily_vol(daily["close"]).set_axis(close.index))
    return cache[asset]


def _resolve(asset: str, as_of, horizon_days: int, cache: dict):
    close, sigma = _bars(cache, asset)
    as_of = pd.Timestamp(as_of).tz_convert("UTC")
    known = close.index[close.index <= as_of]
    if len(known) == 0:
        return None
    issue_t = known[-1]
    target_t = issue_t + pd.Timedelta(days=horizon_days)
    if close.index[-1] < target_t:
        return None                                              # horizon has not fully passed on closed bars
    ret = float(close.loc[target_t] / close.loc[issue_t] - 1.0)
    sig = float(sigma.loc[issue_t])
    return ret, sig, issue_t


def score(now=None) -> dict:
    """Read pending insights, compute outcomes with NO database lock held (loading bars takes its own lock), then write."""
    now = now or utcnow()
    out = {"views_resolved": 0, "flags_resolved": 0, "pending": 0}
    with connect() as con:
        rows = con.execute(
            "SELECT i.insight_id, i.as_of, i.asset, i.payload FROM insights i LEFT JOIN insight_outcomes o ON o.insight_id = i.insight_id "
            "WHERE o.insight_id IS NULL AND json_extract_string(i.payload, '$.kind') IN ('shadow_view', 'risk_flag') ORDER BY i.seq").fetchall()
    cache: dict = {}
    resolved: list[tuple] = []
    for insight_id, as_of, asset, payload in rows:
        p = json.loads(payload)
        if asset not in SYMBOLS:
            continue
        if p["kind"] == "shadow_view":
            h = int(p["horizon_days"])
            r = _resolve(asset, as_of, h, cache)
            if r is None:
                out["pending"] += 1
                continue
            ret, sig, issue_t = r
            band = sig * math.sqrt(h)
            hit = ret > 0 if p["direction"] == "up" else ret < 0 if p["direction"] == "down" else abs(ret) <= band
            resolved.append((insight_id, now, h, ret, bool(hit), json.dumps({"sigma_daily": sig, "issue": str(issue_t)})))
            out["views_resolved"] += 1
        else:
            r = _resolve(asset, as_of, FLAG_HORIZON, cache)
            if r is None:
                out["pending"] += 1
                continue
            ret, sig, issue_t = r
            hit = abs(ret) >= FLAG_SIGMAS * sig * math.sqrt(FLAG_HORIZON)
            resolved.append((insight_id, now, FLAG_HORIZON, ret, bool(hit), json.dumps({"sigma_daily": sig, "severity": p["severity"]})))
            out["flags_resolved"] += 1
    if resolved:
        with connect() as con:
            con.executemany("INSERT INTO insight_outcomes VALUES (?,?,?,?,?,?)", resolved)
    emit("agents.score_run", service=SERVICE, **out)
    return out


def _card(rows) -> dict:
    views = [r for r in rows if r[0] == "shadow_view"]
    flags = [r for r in rows if r[0] == "risk_flag"]
    return {
        "views": len(views), "view_hit_rate": (sum(r[3] for r in views) / len(views)) if views else None,
        "flags": len(flags), "flag_followed_by_large_move_rate": (sum(r[3] for r in flags) / len(flags)) if flags else None,
    }


def scorecard(con) -> dict:
    """Overall results plus a breakdown by who produced the insight (briefing or investigator), so each earns trust separately."""
    rows = con.execute(
        "SELECT json_extract_string(i.payload, '$.kind'), json_extract_string(i.payload, '$.direction'), "
        "CAST(json_extract(i.payload, '$.confidence') AS DOUBLE), o.hit, o.realized_return, "
        "COALESCE(json_extract_string(i.payload, '$.source'), 'briefing') "
        "FROM insight_outcomes o JOIN insights i ON i.insight_id = o.insight_id").fetchall()
    card = _card(rows)
    card["by_source"] = {s: _card([r for r in rows if r[5] == s]) for s in sorted({r[5] for r in rows})}
    return card
