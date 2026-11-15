"""The desk packet: everything a trader would look at before deciding, computed locally and deterministically (no model, no network).

The trader agent (agents/trader.py) reads this packet. Forecasts, signals, news and the model channels are inputs in it, side by side with
the portfolio, the risk limits, the costs and the agent's own track record. Nothing here decides anything.

Honesty is part of the packet: each signal family carries the verdict of our own pre-registered tests (SIGNAL_RECORD), so the trader knows
which inputs have earned trust and which have not. Numbers are rounded; text that came from the internet was already classified into
structured fields by another model and anything flagged as suspicious is withheld (see agents/briefing.gather_events).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..eval import features
from ..eval.costs import CostModel
from ..eval.data import load_bars
from ..obs.events import utcnow
from ..store.db import connect
from ..trading import book, limits as L
from ..trading.types import DEFAULT_RULES
from . import briefing

SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
HOURLY_MIN_BARS = 24 * 8

# What our own pre-registered tests found, so the trader weighs each input by what it has earned. Sources are repo documents.
SIGNAL_RECORD = {
    "daily_trend (2 of 3 EMA pairs up)": "The only rule with a decent risk-adjusted result (gated, daily, long-only: Sharpe about 0.5 to 0.95 depending on sizing), but never cleared the pre-registered bar (docs/phase4-voltarget-entry.md). Buy and hold earned far more over 2020-2026. Weak evidence of value as a filter, none as a timing tool.",
    "forecasters (Kronos, Chronos-2, TimesFM)": "None beat a random walk walk-forward on BTC or ETH (docs/forecast-eval.md). Treat any forecast as noise unless it agrees with independent evidence.",
    "PI-Net / ML fusion": "No detectable edge in any pre-registered variant, with or without news and Chronos-2 (docs/news-forecast-results.md).",
    "news volume and tone (GDELT)": "Event study found 3 of 96 nominal hits against about 4.8 expected by chance (docs/news-study.md). Useful for awareness of catalysts, not as a timing signal.",
    "hourly breakout (24-bar high/low with EMA filter)": "Lost money after costs, long and short, with and without leverage (docs/phase5-futures-breakout*.md). Not a reason to enter on its own.",
    "hourly mean reversion (+-2.5 sigma fade)": "No gross edge: after long signals the average 24 h move was about zero, after short signals price kept rising (docs/phase5-futures-reversion.md).",
    "shorting": "Short trades lost money in every hourly study on this sample (crypto drifted up). Shorting is also switched off in the approved limits.",
}

SESSIONS = ((0, 7, "Asia"), (7, 13, "Europe"), (13, 21, "US"), (21, 24, "late US / Asia open"))


def _r(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def session(now: datetime) -> str:
    return next(name for a, b, name in SESSIONS if a <= now.hour < b)


def _hourly_view(h: pd.DataFrame, now: datetime) -> dict:
    """Closed hourly bars only. Signals are described as facts about the current state, not as recommendations."""
    h = h[h.index + pd.Timedelta(hours=1) <= pd.Timestamp(now)]
    if len(h) < HOURLY_MIN_BARS:
        return {"error": "not enough closed hourly bars"}
    c, hi, lo, vol = h["close"], h["high"], h["low"], h["volume"]
    last = float(c.iloc[-1])
    r1 = c.pct_change()
    tr = pd.concat([hi - lo, (hi - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
    atr24 = float(tr.rolling(24).mean().iloc[-1])
    mu48, sd48 = float(c.rolling(48).mean().iloc[-1]), float(c.rolling(48).std().iloc[-1])
    ema12, ema48 = float(c.ewm(span=12, adjust=False).mean().iloc[-1]), float(c.ewm(span=48, adjust=False).mean().iloc[-1])
    hi24, lo24 = float(hi.iloc[-24:].max()), float(lo.iloc[-24:].min())
    hi7, lo7 = float(hi.iloc[-168:].max()), float(lo.iloc[-168:].min())
    prior_hi, prior_lo = float(hi.iloc[-25:-1].max()), float(lo.iloc[-25:-1].min())
    day = h.iloc[-24:]
    return {
        "last_closed_bar_open": f"{h.index[-1]:%Y-%m-%d %H:%M}", "price": _r(last, 2),
        "ret_1h": _r(c.iloc[-1] / c.iloc[-2] - 1), "ret_4h": _r(c.iloc[-1] / c.iloc[-5] - 1), "ret_24h": _r(c.iloc[-1] / c.iloc[-25] - 1), "ret_7d": _r(c.iloc[-1] / c.iloc[-169] - 1),
        "realised_vol_24h_annual": _r(float(r1.iloc[-24:].std()) * math.sqrt(24 * 365), 3), "realised_vol_7d_annual": _r(float(r1.iloc[-168:].std()) * math.sqrt(24 * 365), 3),
        "atr_24h_pct_of_price": _r(atr24 / last), "volume_vs_7d_avg": _r(float(vol.iloc[-24:].mean() / vol.iloc[-168:].mean()), 2),
        "range_position_24h": _r((last - lo24) / (hi24 - lo24) if hi24 > lo24 else 0.5, 2), "range_position_7d": _r((last - lo7) / (hi7 - lo7) if hi7 > lo7 else 0.5, 2),
        "levels": {"high_24h": _r(hi24, 2), "low_24h": _r(lo24, 2), "high_7d": _r(hi7, 2), "low_7d": _r(lo7, 2)},
        "state_facts": {
            "z_vs_48h_mean": _r((last - mu48) / sd48 if sd48 > 0 else 0.0, 2), "ema12_above_ema48": bool(ema12 > ema48),
            "closed_above_prior_24h_high": bool(last > prior_hi), "closed_below_prior_24h_low": bool(last < prior_lo),
            "last_24h_up_bars": int((day["close"] > day["open"]).sum()),
        },
    }


def _daily_view(d: pd.DataFrame) -> dict:
    f = features.market_features(d).iloc[-1]
    c = d["close"]
    return {
        "last_closed_day": str(d.index[-1].date()), "close": _r(float(c.iloc[-1]), 2),
        "ret_1d": _r(f["ret_1"]), "ret_5d": _r(f["ret_5"]), "ret_20d": _r(f["ret_20"]), "ret_60d": _r(f["ret_60"]),
        "vol_20d_annual": _r(float(f["vol_20"]) * math.sqrt(365), 3), "trend_votes_of_3": _r(float(f["trend_votes"]) * 3, 1),
        "dist_from_ema16": _r(f["dist_ema_16"]), "dist_from_ema64": _r(f["dist_ema_64"]), "drawdown_from_90d_high": _r(f["drawdown_90"]),
        "volume_z_20d": _r(f["volume_z"], 2), "prior_day_high": _r(float(d["high"].iloc[-1]), 2), "prior_day_low": _r(float(d["low"].iloc[-1]), 2),
        "high_30d": _r(float(d["high"].iloc[-30:].max()), 2), "low_30d": _r(float(d["low"].iloc[-30:].min()), 2),
    }


def _forecast_view(sym: str, daily: pd.DataFrame) -> dict:
    """The newest cached walk-forward forecast per model: probability that the return over each horizon is positive. Flagged when stale."""
    from ..forecast.base import HORIZONS, load_cache
    from ..forecast.features import prob_up

    out = {}
    for model in ("chronos2", "kronos_small", "timesfm25"):
        try:
            cache = load_cache(model, sym)
        except Exception as exc:                                        # a broken cache is reported, never fatal
            out[model] = {"error": f"{type(exc).__name__}"}
            continue
        if cache is None or len(cache) == 0:
            continue
        origin = pd.Timestamp(cache.origins[-1])
        age_days = (daily.index[-1].tz_localize(None) - origin).days
        out[model] = {"origin": str(origin.date()), "stale": bool(age_days > 2),
                      "prob_up": {f"{h}d": _r(float(prob_up(cache.cube[-1:, j, :])[0]), 2) for j, h in enumerate(HORIZONS)}}
    return out or {"note": "no cached forecasts"}


def _news_view(now: datetime) -> dict:
    with connect() as con:
        events, withheld = briefing.gather_events(con, 24)
        flags = con.execute(
            "SELECT as_of, asset, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'risk_flag' AND epoch(as_of) >= ? ORDER BY seq DESC LIMIT 12",
            [(now - timedelta(hours=48)).timestamp()]).fetchall()
        brief = con.execute("SELECT as_of, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'briefing' ORDER BY seq DESC LIMIT 1").fetchone()
        inv = con.execute("SELECT as_of, evidence, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'investigation_finding' AND epoch(as_of) >= ? ORDER BY seq DESC LIMIT 8",
                          [(now - timedelta(hours=72)).timestamp()]).fetchall()
    out = {
        "events_24h": events[:25], "withheld_as_suspicious": withheld,
        "risk_flags_48h": [{"as_of": f"{a:%Y-%m-%d %H:%M}", "asset": asset, **{k: json.loads(p)[k] for k in ("flag", "severity", "reason") if k in json.loads(p)}} for a, asset, p in flags],
        "calendar": "no economic calendar source is connected: scheduled releases (CPI, FOMC, ETF decisions) are NOT visible here, so check the date yourself and widen caution on likely event days",
    }
    if brief:
        p = json.loads(brief[1])
        out["latest_briefing"] = {"as_of": f"{brief[0]:%Y-%m-%d %H:%M}", "headline": p["headline"], "regime": p["regime"], "summary": p["summary"][:700]}
    if inv:
        out["investigator_findings_72h"] = [{"as_of": f"{a:%Y-%m-%d %H:%M}", **{k: json.loads(p).get(k) for k in ("claim", "direction", "confidence")}} for a, _e, p in inv]
    try:
        from ..news import gdelt_timeline as g

        daily, _info = g.load_daily(partial=True)
        z = g.news_features(daily).iloc[-1]
        top = z.abs().sort_values(ascending=False).head(6).index
        out["gdelt_attention_z_scores"] = {k: _r(float(z[k]), 2) for k in top}
        out["gdelt_last_day"] = str(daily.index[-1].date())
    except Exception:
        pass
    return out


def _portfolio_view(now: datetime) -> dict:
    state = book.load_state(list(SYMBOLS.values()), now)
    lim, why = L.load()
    cm = CostModel()
    positions = []
    for sym, p in state.positions.items():
        mark = state.prices.get(sym, (p.avg_price, 0, ""))[0]
        risk = p.qty * (p.avg_price - p.stop_price) if p.stop_price else None
        positions.append({"symbol": sym, "side": p.side, "qty": p.qty, "avg_price": _r(p.avg_price, 2), "mark": _r(mark, 2), "unrealised_pct": _r(mark / p.avg_price - 1),
                          "stop": _r(p.stop_price, 2), "take_profit": _r(p.take_profit, 2), "age_hours": _r((now - p.entry_ts).total_seconds() / 3600, 1) if p.entry_ts else None,
                          "notional": _r(p.qty * mark, 2), "dollars_at_risk_to_stop": _r(risk, 2)})
    pending = [{"order_id": o["order_id"], "symbol": o["symbol"], "side": o["side"], "qty": o["qty"], "status": o["status"]} for o in book.list_orders(10, "paper") if o["status"] == "proposed"]
    dd = (state.peak_equity - state.equity) / state.peak_equity if state.peak_equity > 0 else 0.0
    return {
        "equity": _r(state.equity, 2), "cash": _r(state.cash, 2), "exposure_fraction": _r(state.exposure / state.equity if state.equity > 0 else 0.0),
        "drawdown_from_peak": _r(dd), "today_pnl_fraction": _r(state.equity / state.day_start_equity - 1 if state.day_start_equity > 0 else 0.0),
        "positions": positions, "pending_proposals": pending, "halted": state.halt_latched, "killed": state.killed,
        "btc_eth_note": "BTC and ETH are highly correlated (see correlation_30d): two positions are closer to one bet than two",
        "limits": ({"profile": lim.profile, "max_exposure_fraction": lim.max_exposure_fraction, "account_drawdown_halt": lim.account_drawdown_halt, "daily_loss_halt": lim.daily_loss_halt,
                    "risk_per_trade": lim.risk_per_trade, "max_leverage": lim.max_leverage, "allow_short": lim.allow_short} if lim else {"unavailable": why}),
        "gate_facts": {"round_trip_cost_pct": _r(cm.round_trip() * 100, 2), "cost_gate": f"round-trip costs may not exceed {L.MAX_COST_R}R, so a stop must be at least {cm.round_trip() / L.MAX_COST_R * 100:.2f}% from price",
                       "stop_range_pct": [L.MIN_STOP_FRACTION * 100, L.MAX_STOP_FRACTION * 100], "one_position_per_symbol": True, "adding_to_a_position": False,
                       "min_notional": {s: r.min_notional for s, r in DEFAULT_RULES.items()}},
    }


def build_packet(now: datetime | None = None, journal: dict | None = None) -> dict:
    """The packet. `journal` is supplied by the trader (its own recent calls and scores) so this module stays free of scoring imports."""
    now = now or utcnow()
    markets, daily_frames = {}, {}
    for asset, sym in SYMBOLS.items():
        daily = load_bars(sym, "1d")
        daily_frames[asset] = daily
        markets[asset] = {"daily": _daily_view(daily), "hourly": _hourly_view(load_bars(sym, "1h"), now), "forecasts": _forecast_view(sym, daily)}
    btc, eth = daily_frames["BTC"]["close"].pct_change(), daily_frames["ETH"]["close"].pct_change()
    cross = {"correlation_30d": _r(float(btc.iloc[-30:].corr(eth.iloc[-30:])), 2),
             "eth_vs_btc_5d": _r((1 + eth.iloc[-5:]).prod() - (1 + btc.iloc[-5:]).prod()), "eth_vs_btc_20d": _r((1 + eth.iloc[-20:]).prod() - (1 + btc.iloc[-20:]).prod())}
    packet = {
        "as_of_utc": f"{now:%Y-%m-%d %H:%M}", "weekday": now.strftime("%A"), "session": session(now), "markets": markets, "cross_asset": cross,
        "news": _news_view(now), "signal_track_record": SIGNAL_RECORD, "portfolio": _portfolio_view(now),
        "journal": journal or {"note": "no previous trade ideas yet"},
    }
    return packet


def packet_text(packet: dict) -> str:
    return json.dumps(packet, indent=1, default=str)
