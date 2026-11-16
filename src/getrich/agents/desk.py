"""The desk packet: everything a trader would look at before deciding, computed locally and deterministically (no model, no network).

The trader agent (agents/trader.py) reads this packet. Forecasts, signals, news and the model channels are inputs in it, side by side with
the whole tradable universe (crypto, forex, gold and silver, trading/instruments.py), the portfolio, the risk limits, the costs and the agent's own
track record. Nothing here decides anything. The trader chooses what to trade and, as often, what not to.

Honesty is part of the packet: each signal family carries the verdict of our own pre-registered tests (SIGNAL_RECORD), so the trader knows which
inputs have earned trust and which have not. Numbers are rounded; text that came from the internet was already classified into structured fields
by another model and anything flagged as suspicious is withheld (see agents/briefing.gather_events).

Layout: a compact `universe` row for every instrument (so the trader can compare and pick), full detail for the core pair, anything held, and the
few non-core instruments that moved most in volatility-adjusted terms today, and the shared news, portfolio and journal sections.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from ..eval import features
from ..eval.data import load_bars
from ..obs.events import utcnow
from ..store.db import connect
from ..trading import book, instruments, limits as L
from ..trading.types import DEFAULT_RULES
from . import briefing

def _utc(ts) -> str:
    """A stored timestamp as UTC text. The store hands back the container's local time (Asia/Colombo here); the packet says UTC everywhere."""
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.astimezone(timezone.utc)
    return f"{ts:%Y-%m-%d %H:%M}"


HOURLY_MIN_BARS = 24 * 8
DETAIL_EXTRA = 4                       # non-core, non-held instruments shown in full: the biggest moves in volatility terms
STALE_HOURS = 96.0                     # older than this (a weekend is about 50 h) and the instrument is shown as unavailable
FRESH_HOURS = 3.0                      # an hourly bar older than this (market open) means the data feed is behind
HOURS_PER_YEAR = {"crypto": 24 * 365, "fx": 24 * 5 * 52, "metal": 23 * 5 * 52}
DAYS_PER_YEAR = {"crypto": 365, "fx": 260, "metal": 260}

# What our own pre-registered tests found, so the trader weighs each input by what it has earned. Sources are repo documents.
SIGNAL_RECORD = {
    "daily_trend (2 of 3 EMA pairs up)": "The only rule with a decent risk-adjusted result (gated, daily, long-only, BTC and ETH only: Sharpe about 0.5 to 0.95 depending on sizing), but never cleared the pre-registered bar (docs/phase4-voltarget-entry.md). Buy and hold earned far more over 2020-2026. Weak evidence of value as a filter, none as a timing tool. Never tested on forex or gold.",
    "forecasters (Kronos, Chronos-2, TimesFM)": "None beat a random walk walk-forward on BTC or ETH (docs/forecast-eval.md). Treat any forecast as noise unless it agrees with independent evidence. They exist only for BTC and ETH.",
    "PI-Net / ML fusion": "No detectable edge in any pre-registered variant, with or without news and Chronos-2 (docs/news-forecast-results.md). BTC and ETH only. A frozen copy now scores BTC and ETH every day and is being scored forward in a pre-registered study (docs/preregistration-pinet-forward.md); the verdict is not due before about 180 days, so treat its score as noise until then.",
    "news volume and tone (GDELT)": "Event study found 3 of 96 nominal hits against about 4.8 expected by chance (docs/news-study.md). Useful for awareness of catalysts, not as a timing signal.",
    "hourly breakout (24-bar high/low with EMA filter)": "Lost money after costs on BTC and ETH, long and short, with and without leverage (docs/phase5-futures-breakout*.md). Not a reason to enter on its own. Untested on forex.",
    "hourly mean reversion (+-2.5 sigma fade)": "No gross edge on BTC and ETH: after long signals the average 24 h move was about zero, after short signals price kept rising (docs/phase5-futures-reversion.md). Untested on forex.",
    "shorting": "Short trades lost money in every hourly study on this sample (crypto drifted up). Shorting is also switched off in the approved limits, so only long ideas can become proposals; short ideas are recorded and scored as hypotheticals.",
    "forex and metals": "No study of ours has covered forex, gold or silver. Free data is a Yahoo feed (hourly for about two years), not a trading tape; costs are assumptions; overnight swaps are not modelled. Anything you conclude about them rests on general market knowledge, not on tested evidence here.",
}

SESSIONS = ((0, 7, "Asia"), (7, 13, "Europe"), (13, 21, "US"), (21, 24, "late US / Asia open"))


def _r(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def session(now: datetime) -> str:
    return next(name for a, b, name in SESSIONS if a <= now.hour < b)


def _bars(symbol: str, timeframe: str) -> pd.DataFrame:
    return load_bars(symbol, timeframe, venue=instruments.bar_venue(symbol))


def _hourly_view(h: pd.DataFrame, now: datetime, cls: str = "crypto") -> dict:
    """Closed hourly bars only. Signals are described as facts about the current state, not as recommendations."""
    h = h[h.index + pd.Timedelta(hours=1) <= pd.Timestamp(now)]
    if len(h) < HOURLY_MIN_BARS:
        return {"error": "not enough closed hourly bars"}
    ann = math.sqrt(HOURS_PER_YEAR[cls])
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
    v7 = float(vol.iloc[-168:].mean())
    return {
        "last_closed_bar_open": f"{h.index[-1]:%Y-%m-%d %H:%M}", "price": _r(last, 6 if last < 10 else 2),
        "ret_1h": _r(c.iloc[-1] / c.iloc[-2] - 1), "ret_4h": _r(c.iloc[-1] / c.iloc[-5] - 1), "ret_24h": _r(c.iloc[-1] / c.iloc[-25] - 1), "ret_7d": _r(c.iloc[-1] / c.iloc[-169] - 1),
        "realised_vol_24h_annual": _r(float(r1.iloc[-24:].std()) * ann, 3), "realised_vol_7d_annual": _r(float(r1.iloc[-168:].std()) * ann, 3),
        "atr_24h_pct_of_price": _r(atr24 / last), "volume_vs_7d_avg": _r(float(vol.iloc[-24:].mean() / v7), 2) if v7 > 0 else None,
        "range_position_24h": _r((last - lo24) / (hi24 - lo24) if hi24 > lo24 else 0.5, 2), "range_position_7d": _r((last - lo7) / (hi7 - lo7) if hi7 > lo7 else 0.5, 2),
        "levels": {"high_24h": _r(hi24, 6 if last < 10 else 2), "low_24h": _r(lo24, 6 if last < 10 else 2), "high_7d": _r(hi7, 6 if last < 10 else 2), "low_7d": _r(lo7, 6 if last < 10 else 2)},
        "state_facts": {
            "z_vs_48h_mean": _r((last - mu48) / sd48 if sd48 > 0 else 0.0, 2), "ema12_above_ema48": bool(ema12 > ema48),
            "closed_above_prior_24h_high": bool(last > prior_hi), "closed_below_prior_24h_low": bool(last < prior_lo),
            "last_24h_up_bars": int((day["close"] > day["open"]).sum()),
        },
    }


def _daily_view(d: pd.DataFrame, cls: str = "crypto") -> dict:
    f = features.market_features(d).iloc[-1]
    c = d["close"]
    nd = 6 if float(c.iloc[-1]) < 10 else 2
    return {
        "last_closed_day": str(d.index[-1].date()), "close": _r(float(c.iloc[-1]), nd),
        "ret_1d": _r(f["ret_1"]), "ret_5d": _r(f["ret_5"]), "ret_20d": _r(f["ret_20"]), "ret_60d": _r(f["ret_60"]),
        "vol_20d_annual": _r(float(f["vol_20"]) * math.sqrt(DAYS_PER_YEAR[cls]), 3), "trend_votes_of_3": _r(float(f["trend_votes"]) * 3, 1),
        "dist_from_ema16": _r(f["dist_ema_16"]), "dist_from_ema64": _r(f["dist_ema_64"]), "drawdown_from_90d_high": _r(f["drawdown_90"]),
        "volume_z_20d": _r(f["volume_z"], 2), "prior_day_high": _r(float(d["high"].iloc[-1]), nd), "prior_day_low": _r(float(d["low"].iloc[-1]), nd),
        "high_30d": _r(float(d["high"].iloc[-30:].max()), nd), "low_30d": _r(float(d["low"].iloc[-30:].min()), nd),
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
    return out or {"note": "no cached forecasts for this instrument"}


def _scan_row(inst: instruments.Instrument, daily: pd.DataFrame, hourly: pd.DataFrame, now: datetime) -> dict:
    """One compact line per instrument so the trader can compare the whole universe at a glance."""
    cls = inst.asset_class
    hv = _hourly_view(hourly, now, cls)
    if "error" in hv:
        return {"name": inst.name, "class": cls, "available": False, "why": hv["error"]}
    closed = hourly[hourly.index + pd.Timedelta(hours=1) <= pd.Timestamp(now)]
    age_h = (pd.Timestamp(now) - (closed.index[-1] + pd.Timedelta(hours=1))).total_seconds() / 3600
    if age_h > STALE_HOURS:                                              # a feed that is days behind (or still backfilling) says nothing about now
        return {"name": inst.name, "class": cls, "available": False, "why": f"hourly data is {age_h / 24:.0f} days old: run the collector"}
    dv = _daily_view(daily, cls)
    open_now = instruments.is_open(inst.symbol, now)
    fresh = age_h <= FRESH_HOURS
    rules = DEFAULT_RULES[inst.symbol]
    rt = inst.cost.round_trip()
    daily_sigma = (dv["vol_20d_annual"] or 0) / math.sqrt(DAYS_PER_YEAR[cls])
    move_sigma = (hv["ret_24h"] or 0) / daily_sigma if daily_sigma else None
    return {
        "name": inst.name, "class": cls, "available": True, "can_open_now": bool(open_now and fresh), "market_open": bool(open_now), "data_age_hours": _r(age_h, 1),
        "price": hv["price"], "last_closed_bar_open": hv["last_closed_bar_open"], "ret_24h": hv["ret_24h"], "ret_7d": hv["ret_7d"], "ret_20d": dv["ret_20d"],
        "move_24h_in_daily_sigmas": _r(move_sigma, 2), "vol_20d_annual": dv["vol_20d_annual"], "atr_24h_pct": hv["atr_24h_pct_of_price"],
        "trend_votes_of_3": dv["trend_votes_of_3"], "drawdown_from_90d_high": dv["drawdown_from_90d_high"], "range_position_7d": hv["range_position_7d"],
        "z_vs_48h_mean": hv["state_facts"]["z_vs_48h_mean"], "hourly_trend_up": hv["state_facts"]["ema12_above_ema48"], "round_trip_cost_pct": _r(rt * 100, 3),
        "min_stop_pct": _r(max(rules.min_stop_fraction, rt / L.MAX_COST_R) * 100, 2), "note": inst.note or None,
    }


def _with_ages(events: list[dict], now: datetime) -> list[dict]:
    """Each event gets `published_hours_ago` (when the story came out, not when it was classified), so the trader can tell breaking news from old news."""
    if not events:
        return events
    with connect() as con:
        marks = ",".join("?" for _ in events)
        pub = dict(con.execute(f"SELECT item_id, coalesce(published_at, ingested_at) FROM news_items WHERE item_id IN ({marks})", [e["ref"] for e in events]).fetchall())
    out = []
    for e in events:
        t = pub.get(e["ref"])
        out.append({**e, "published_hours_ago": round(max((now - t).total_seconds() / 3600, 0.0), 1) if t is not None else None})
    return out


def _news_view(now: datetime) -> dict:
    with connect() as con:
        events, withheld = briefing.gather_events(con, 24)
        flags = con.execute(
            "SELECT as_of, asset, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'risk_flag' AND epoch(as_of) >= ? ORDER BY seq DESC LIMIT 12",
            [(now - timedelta(hours=48)).timestamp()]).fetchall()
        brief = con.execute("SELECT as_of, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'briefing' ORDER BY seq DESC LIMIT 1").fetchone()
        inv = con.execute("SELECT as_of, evidence, payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'investigation_finding' AND epoch(as_of) >= ? ORDER BY seq DESC LIMIT 8",
                          [(now - timedelta(hours=72)).timestamp()]).fetchall()
    events = _with_ages(events[:25], now)
    out = {
        "events_24h": events, "withheld_as_suspicious": withheld,
        "risk_flags_48h": [{"as_of": _utc(a), "asset": asset, **{k: json.loads(p)[k] for k in ("flag", "severity", "reason") if k in json.loads(p)}} for a, asset, p in flags],
        "calendar": "no economic calendar source is connected: scheduled releases (CPI, FOMC, ECB, BoJ, payrolls, ETF decisions) are NOT visible here, so check the date yourself and widen caution on likely event days. Forex and gold react most to exactly these releases.",
        "note": "event assets use currency and asset tags (USD, EUR, JPY, GOLD, BTC...); map them to the instruments yourself",
    }
    if brief:
        p = json.loads(brief[1])
        out["latest_briefing"] = {"as_of": _utc(brief[0]), "headline": p["headline"], "regime": p["regime"], "summary": p["summary"][:700]}
    if inv:
        out["investigator_findings_72h"] = [{"as_of": _utc(a), **{k: json.loads(p).get(k) for k in ("claim", "direction", "confidence")}} for a, _e, p in inv]
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


def _age_h(ts, now: datetime) -> float | None:
    return None if ts is None else round((now - ts).total_seconds() / 3600, 1)


def news_freshness(now: datetime) -> dict:
    """How old the news inputs are, in hours: the newest story, the newest classified event, the unclassified backlog and the briefing."""
    with connect() as con:
        newest_item = con.execute("SELECT max(coalesce(published_at, ingested_at)) FROM news_items WHERE source NOT IN ('desk_packet', 'investigator_evidence') "
                                  "AND coalesce(published_at, ingested_at) <= ?", [now]).fetchone()[0]          # exchange maintenance notices are dated in the future
        newest_event = con.execute("SELECT max(as_of) FROM insights WHERE json_extract_string(payload, '$.kind') = 'event_extraction'").fetchone()[0]
        backlog = con.execute("SELECT count(*) FROM news_items n LEFT JOIN item_processing p ON p.item_id = n.item_id WHERE p.item_id IS NULL AND n.ingested_at >= ?",
                              [now - timedelta(hours=24)]).fetchone()[0]
        briefing_ts = con.execute("SELECT max(as_of) FROM insights WHERE json_extract_string(payload, '$.kind') = 'briefing'").fetchone()[0]
    return {"newest_story_hours_ago": _age_h(newest_item, now), "newest_classified_event_hours_ago": _age_h(newest_event, now),
            "stories_from_last_24h_not_yet_classified": backlog, "briefing_hours_old": _age_h(briefing_ts, now)}


def _pinet_view(sym: str) -> dict:
    """The frozen PI-Net's newest call for this coin: take or skip when the trend rule is long (its domain), else out of domain. Shadow only."""
    try:
        from ..eval import pinet_live

        got = pinet_live.latest().get(sym)
    except Exception as exc:
        return {"error": type(exc).__name__}
    if not got:
        return {"note": "no PI-Net decision recorded yet"}
    return {**got, "status": "frozen model, scored forward in a pre-registered study; no demonstrated edge, do not rely on it"}


def _pinet_freshness() -> dict:
    out = {"what": "a frozen LightGBM model (trained on 2021 to 2026-10-25) scores a long entry for BTC and ETH on days when the trend rule is long; take means expected net R above zero",
           "status": "forward study in progress (docs/preregistration-pinet-forward.md): not an input until it shows value"}
    try:
        from ..eval import pinet_live

        v = pinet_live.verdict(pinet_live.records())
        s = v["summary"]
        out["study"] = {"decisions": s["decisions"], "resolved": s["resolved"], "take_resolved": s["take"], "mean_net_r_take": None if s["mean_take"] is None else round(s["mean_take"], 2),
                        "mean_net_r_all": None if s["mean_all"] is None else round(s["mean_all"], 2), "verdict_due": v["due"], "days_since_first": v["days_since_first"],
                        "note": "interim numbers, not a verdict" if not v["due"] else "checkpoint reached"}
        if v["due"]:
            out["study"]["shows_value"] = v["shows_value"]
    except Exception as exc:
        out["error"] = type(exc).__name__
    return out


def _forecaster_freshness() -> dict:
    """Newest forecast origin per model and symbol, and how many days behind the newest daily bar it is (the models service adds one a day)."""
    out = {"covers": "BTCUSDT and ETHUSDT only",
           "note": "a separate models service adds one forecast per model and symbol after each daily bar closes; a run does not compute them. Each forecast shows its origin date and a stale flag"}
    try:
        from ..forecast import live

        out["newest_origin"] = {f"{r['model']}/{r['symbol']}": {"origin": r.get("newest_origin"), "days_behind": r.get("days_behind")} for r in live.status()}
    except Exception as exc:                                                     # never let a cache problem stop a plan
        out["error"] = type(exc).__name__
    return out


def _freshness(now: datetime, scan: dict, refresh: dict | None) -> dict:
    """How old every input is, in plain hours, and what the pre-run refresh managed to do. The trader is told to discount what is stale."""
    ages = [r["data_age_hours"] for r in scan.values() if r.get("available") and r.get("data_age_hours") is not None]
    return {
        "market_data": {"hourly_bar_age_hours": {"newest": min(ages), "oldest": max(ages)} if ages else None},
        "news": news_freshness(now),
        "forecasters": _forecaster_freshness(),
        "pinet": _pinet_freshness(),
        "refresh_before_this_run": refresh if refresh is not None else {"ran": False},
    }


def _portfolio_view(now: datetime) -> dict:
    state = book.load_state(instruments.symbols(), now)
    lim, why = L.load()
    positions = []
    for sym, p in state.positions.items():
        mark = state.prices.get(sym, (p.avg_price, 0, ""))[0]
        risk = p.qty * (p.avg_price - p.stop_price) if p.stop_price else None
        positions.append({"symbol": sym, "side": p.side, "qty": p.qty, "avg_price": _r(p.avg_price, 6), "mark": _r(mark, 6), "unrealised_pct": _r(mark / p.avg_price - 1),
                          "stop": _r(p.stop_price, 6), "take_profit": _r(p.take_profit, 6), "age_hours": _r((now - p.entry_ts).total_seconds() / 3600, 1) if p.entry_ts else None,
                          "notional": _r(p.qty * mark, 2), "dollars_at_risk_to_stop": _r(risk, 2)})
    pending = [{"order_id": o["order_id"], "symbol": o["symbol"], "side": o["side"], "qty": o["qty"], "status": o["status"]} for o in book.list_orders(10, "paper") if o["status"] == "proposed"]
    dd = (state.peak_equity - state.equity) / state.peak_equity if state.peak_equity > 0 else 0.0
    return {
        "equity": _r(state.equity, 2), "cash": _r(state.cash, 2), "exposure_fraction": _r(state.exposure / state.equity if state.equity > 0 else 0.0),
        "drawdown_from_peak": _r(dd), "today_pnl_fraction": _r(state.equity / state.day_start_equity - 1 if state.day_start_equity > 0 else 0.0),
        "positions": positions, "pending_proposals": pending, "halted": state.halt_latched, "killed": state.killed,
        "correlation_note": "Crypto majors move together (BTC and ETH about 0.9). Dollar pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD, and the inverse JPYUSD, CADUSD, CHFUSD) all share one driver, the dollar, and gold often moves against it. Several positions on one driver are one bet; the gate does not check this, you must.",
        "limits": ({"profile": lim.profile, "max_exposure_fraction": lim.max_exposure_fraction, "account_drawdown_halt": lim.account_drawdown_halt, "daily_loss_halt": lim.daily_loss_halt,
                    "risk_per_trade": lim.risk_per_trade, "max_leverage": lim.max_leverage, "allow_short": lim.allow_short} if lim else {"unavailable": why}),
        "gate_facts": {"cost_gate": f"round-trip costs may not exceed {L.MAX_COST_R}R, so the minimum stop is round-trip cost / {L.MAX_COST_R} (see min_stop_pct per instrument)",
                       "stop_max_pct": L.MAX_STOP_FRACTION * 100, "one_position_per_symbol": True, "adding_to_a_position": False, "orders_only_when_the_market_is_open_and_data_is_fresh": True,
                       "sizing": "size is the smallest of risk budget, exposure cap, cash and the exchange minimum; with no leverage approved, the exposure cap binds on low-volatility instruments such as forex, so their positions are small"},
    }


def _movers(scan: dict[str, dict], n: int) -> list[str]:
    cands = [(abs(r["move_24h_in_daily_sigmas"] or 0), s) for s, r in scan.items() if r.get("available") and r.get("can_open_now") and not instruments.BY_SYMBOL[s].core]
    return [s for _m, s in sorted(cands, reverse=True)[:n]]


def scan_universe(now: datetime, classes: tuple[str, ...] | None = None) -> tuple[dict, list[str], dict, dict]:
    """(compact row per instrument, symbols with no data yet, daily frames, hourly frames) for the asset classes in scope."""
    classes = tuple(classes) if classes else ("crypto", "fx", "metal")
    daily_frames, hourly_frames, scan, missing = {}, {}, {}, []
    for inst in (i for i in instruments.INSTRUMENTS if i.asset_class in classes):
        try:
            daily_frames[inst.symbol], hourly_frames[inst.symbol] = _bars(inst.symbol, "1d"), _bars(inst.symbol, "1h")
        except ValueError:
            missing.append(inst.symbol)                                 # no data yet: reported, never fatal
            continue
        scan[inst.symbol] = _scan_row(inst, daily_frames[inst.symbol], hourly_frames[inst.symbol], now)
    return scan, missing, daily_frames, hourly_frames


def trader_classes() -> tuple[str, ...]:
    """Which asset classes the trader may look at. GETRICH_TRADER_CLASSES (comma separated: crypto, fx, metal) narrows it; the default is everything."""
    raw = os.environ.get("GETRICH_TRADER_CLASSES", "").strip()
    wanted = tuple(c.strip() for c in raw.split(",") if c.strip())
    return wanted or ("crypto", "fx", "metal")


def build_packet(now: datetime | None = None, journal: dict | None = None, classes: tuple[str, ...] | None = None, refresh: dict | None = None) -> dict:
    """The packet. `journal` is supplied by the trader (its own recent calls and scores) so this module stays free of scoring imports.
    `classes` limits the universe (for example just crypto for now); instruments outside it are not shown at all."""
    now = now or utcnow()
    classes = tuple(classes) if classes else trader_classes()
    scan, missing, daily_frames, hourly_frames = scan_universe(now, classes)
    held = [p.symbol for p in book.load_state(instruments.symbols(), now).positions.values() if p.symbol in scan]
    detail = list(dict.fromkeys([s for s in (i.symbol for i in instruments.INSTRUMENTS if i.core) if s in scan] + [s for s in held if s in scan] + _movers(scan, DETAIL_EXTRA)))
    markets = {}
    for s in detail:
        cls = instruments.BY_SYMBOL[s].asset_class
        markets[s] = {"daily": _daily_view(daily_frames[s], cls), "hourly": _hourly_view(hourly_frames[s], now, cls)}
        if cls == "crypto":
            markets[s]["forecasts"] = _forecast_view(s, daily_frames[s])
            if s in ("BTCUSDT", "ETHUSDT"):
                markets[s]["pinet"] = _pinet_view(s)
    cross = {}
    if "BTCUSDT" in daily_frames and "ETHUSDT" in daily_frames:
        btc, eth = daily_frames["BTCUSDT"]["close"].pct_change(), daily_frames["ETHUSDT"]["close"].pct_change()
        cross["btc_eth_correlation_30d"] = _r(float(btc.iloc[-30:].corr(eth.iloc[-30:])), 2)
        cross["eth_vs_btc_5d"] = _r((1 + eth.iloc[-5:]).prod() - (1 + btc.iloc[-5:]).prod())
    usd_pairs = [s for s in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "JPYUSD", "CADUSD", "CHFUSD") if s in daily_frames]
    if usd_pairs:
        r5 = [float(daily_frames[s]["close"].iloc[-1] / daily_frames[s]["close"].iloc[-6] - 1) for s in usd_pairs]
        cross["dollar_vs_majors_5d"] = {"avg_return_of_the_majors_in_usd": _r(float(np.mean(r5))), "reading": "positive = the dollar weakened against the basket; negative = the dollar strengthened", "pairs": len(usd_pairs)}
    packet = {
        "as_of_utc": f"{now:%Y-%m-%d %H:%M}", "weekday": now.strftime("%A"), "session": session(now),
        "universe": {"in_scope_classes": list(classes), "instruments": scan, "no_data_yet": missing, "how_to_read": "one compact row per instrument; full detail for the core pair, anything held and the biggest movers is in `markets`. You choose which instruments, if any, get an idea."},
        "freshness": _freshness(now, scan, refresh), "markets": markets, "cross_asset": cross, "news": _news_view(now), "signal_track_record": SIGNAL_RECORD, "portfolio": _portfolio_view(now),
        "journal": journal or {"note": "no previous trade ideas yet"},
    }
    return packet


def packet_text(packet: dict) -> str:
    return json.dumps(packet, indent=None, separators=(",", ":"), default=str)
