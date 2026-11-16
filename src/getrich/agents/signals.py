"""The indicator board: the signals we generate, as votes, so a trader can see at a glance how many point up, how many point down, and which have earned trust.

This is NOT a forecast and NOT a trade decision. Each vote is a plain reading of an indicator we already compute, scaled to -1 (bearish) .. +1 (bullish), and each carries
what our own pre-registered tests found about it (`proof`). The score is the plain average of the votes that exist. It says how much the indicators agree; since none of
them has demonstrated an edge, the screens show it as agreement and never as a probability. The trader's own call and the risk gate decide what happens.

Pure functions over numbers already in the desk's universe rows, so they are cheap and testable.
"""

from __future__ import annotations

import math

BUY_ZONE = 0.35
AVOID_ZONE = -0.35
MIN_VOTES = 3

# What our pre-registered tests say about each family (docs/ in the repo). "none" = no demonstrated edge, "weak" = weak evidence as a filter only.
PROOF = {
    "daily_trend": ("weak", "Only rule with a decent risk-adjusted result (BTC and ETH, long-only); never cleared its bar. Not tested on forex."),
    "hourly_trend": ("none", "Hourly breakout and trend entries lost money after costs."),
    "momentum_7d": ("none", "No tested edge as a timing signal."),
    "range_position": ("none", "Position in the week's range: context, not a tested signal."),
    "stretch": ("none", "Mean reversion showed no gross edge on BTC and ETH."),
    "forecasts": ("none", "Kronos, Chronos-2 and TimesFM did not beat a random walk."),
    "pinet": ("none", "No edge in history; being scored forward in a pre-registered study."),
    "news": ("none", "News tone had no detectable timing value in our event study."),
}
LABELS = {
    "daily_trend": "Daily trend (EMA pairs)", "hourly_trend": "Hourly trend (EMA12 vs 48)", "momentum_7d": "7-day momentum", "range_position": "Place in 7-day range",
    "stretch": "Stretch vs 48h mean", "forecasts": "Forecast models (5d)", "pinet": "PI-Net call", "news": "News tone (24h)",
}
MAG = {"high": 1.0, "medium": 0.6, "low": 0.3}


def _clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _vote(id_: str, value: float | None, detail: str) -> dict:
    proof, note = PROOF[id_]
    return {"id": id_, "label": LABELS[id_], "value": None if value is None else round(_clip(value), 2), "detail": detail, "proof": proof, "proof_note": note}


def news_tilt(events: list[dict], symbol: str) -> float | None:
    """Net risk-on versus risk-off tone of the last day's classified events that name this coin or the whole crypto market, in -1..1. None when there are none."""
    base = symbol.removesuffix("USDT")
    total, n = 0.0, 0
    for e in events:
        tags = set(e.get("assets") or [])
        if base not in tags and "CRYPTO_MARKET" not in tags:
            continue
        sign = {"risk_on": 1.0, "risk_off": -1.0}.get(e.get("direction"), 0.0)
        if sign == 0.0:
            continue
        total += sign * MAG.get(e.get("magnitude"), 0.3) * float(e.get("confidence") or 0.5)
        n += 1
    return None if n == 0 else math.tanh(total / 3.0)


def votes(row: dict, extra: dict | None = None) -> list[dict]:
    """`row` is a desk universe row; `extra` may carry hourly_trend_up, forecast_prob_up_5d, pinet_call, news_tilt."""
    extra = extra or {}
    out = []
    tv = row.get("trend_votes_of_3")
    if tv is not None:
        out.append(_vote("daily_trend", (tv - 1.5) / 1.5, f"{tv:g} of 3 EMA pairs up"))
    up = extra.get("hourly_trend_up", row.get("hourly_trend_up"))
    if up is not None:
        out.append(_vote("hourly_trend", 1.0 if up else -1.0, "EMA12 above EMA48" if up else "EMA12 below EMA48"))
    r7, vol = row.get("ret_7d"), row.get("vol_20d_annual")
    if r7 is not None and vol:
        weekly = vol * math.sqrt(7 / (365 if row.get("class") == "crypto" else 260))
        out.append(_vote("momentum_7d", (r7 / weekly) / 2 if weekly else None, f"{r7 * 100:+.1f}% over 7 days"))
    rp = row.get("range_position_7d")
    if rp is not None:
        out.append(_vote("range_position", (rp - 0.5) * 2, f"{rp * 100:.0f}% of the way up the week's range"))
    z = row.get("z_vs_48h_mean")
    if z is not None:
        out.append(_vote("stretch", -z / 2, f"{z:+.1f} sigma from the 48h mean ({'stretched down: bounce candidate' if z <= -1 else 'stretched up: fade candidate' if z >= 1 else 'not stretched'})"))
    p5 = extra.get("forecast_prob_up_5d")
    if p5 is not None:
        out.append(_vote("forecasts", (p5 - 0.5) * 4, f"{p5 * 100:.0f}% average chance of an up move over 5 days"))
    pc = extra.get("pinet_call")
    if pc in ("take", "skip"):
        out.append(_vote("pinet", 1.0 if pc == "take" else -1.0, f"frozen model says {pc}"))
    elif pc == "out_of_domain":
        out.append(_vote("pinet", None, "out of its domain today (trend rule not long)"))
    nt = extra.get("news_tilt")
    if nt is not None:
        out.append(_vote("news", nt, "net risk-on tone" if nt > 0.1 else "net risk-off tone" if nt < -0.1 else "mixed or neutral tone"))
    return out


def board(row: dict, extra: dict | None = None) -> dict:
    vs = votes(row, extra)
    have = [v["value"] for v in vs if v["value"] is not None]
    if len(have) < MIN_VOTES:
        return {"score": None, "zone": "no_read", "votes": vs, "up": 0, "down": 0, "n": len(have)}
    score = sum(have) / len(have)
    zone = "buy" if score >= BUY_ZONE else "avoid" if score <= AVOID_ZONE else "wait"
    return {"score": round(score, 2), "zone": zone, "votes": vs, "up": sum(v > 0.15 for v in have), "down": sum(v < -0.15 for v in have), "n": len(have)}
