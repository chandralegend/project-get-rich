"""Forex, gold and silver bars from Yahoo Finance's public chart endpoint (no key). Closed bars only, stored under venue `yahoo`.

Why Yahoo: it is the one free source that gives hourly bars (about two years) and daily bars (a decade) for the major pairs and for gold and silver
futures. It is unofficial and can throttle or change without notice, so the collector paces its requests, retries throttling patiently and treats
any answer it cannot parse as a failure for that symbol only. Gold and silver are CME futures (GC=F, SI=F) used as proxies for spot. Pairs whose real
quote is not the US dollar are stored inverted (see trading/instruments.py), so every series is quoted in dollars. Forex has no volume: it is stored as 0.
Data quality is the usual free-feed quality: occasional flat or stale bars; nothing here is a trading-grade tape.

This collector is run by hand (`getrich collect-fx`) and is not scheduled or watched by the watchdog.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx

from ..obs.events import emit, utcnow
from ..store.db import connect
from ..trading import instruments

SERVICE = "collector.yahoo"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (getrich-research/0.1)"}
INTERVALS = {"1h": ("1h", timedelta(hours=1), "730d", "5d"), "1d": ("1d", timedelta(days=1), "10y", "1mo")}   # timeframe: (interval, length, first range, update range)
PAUSE_S = 4.0


def parse_chart(payload: dict, instrument, timeframe: str, ingested_at: datetime, now: datetime) -> list[tuple]:
    """Chart JSON to bar tuples. Bars with a missing price are dropped, as is any bar that has not closed yet."""
    result = ((payload or {}).get("chart") or {}).get("result")
    if not result:
        raise ValueError(f"no chart result: {((payload or {}).get('chart') or {}).get('error')}")
    r = result[0]
    q = r["indicators"]["quote"][0]
    length = INTERVALS[timeframe][1]
    out = []
    for i, t in enumerate(r.get("timestamp") or []):
        o, h, l, c = (q[k][i] for k in ("open", "high", "low", "close"))
        if None in (o, h, l, c) or min(o, h, l, c) <= 0:
            continue
        ts = datetime.fromtimestamp(int(t), tz=timezone.utc)
        if ts + length > now:
            continue
        if instrument.invert:
            o, h, l, c = 1 / o, 1 / l, 1 / h, 1 / c                       # a rising USDJPY is a falling JPYUSD, so high and low swap
        out.append(("yahoo", instrument.symbol, timeframe, ts, float(o), float(h), float(l), float(c), 0.0, 0.0, 0, ingested_at))
    return out


def fetch(client: httpx.Client, provider_symbol: str, interval: str, rng: str, *, retries: int = 6, sleep=time.sleep) -> dict:
    """Throttling (HTTP 429, or an empty answer) is retried with growing waits; other errors fail at once."""
    wait = 10.0
    for attempt in range(retries + 1):
        try:
            resp = client.get(URL.format(symbol=provider_symbol), params={"interval": interval, "range": rng})
        except httpx.TransportError:
            if attempt < retries:
                sleep(wait)
                wait = min(wait * 1.6, 120.0)
                continue
            raise
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                pass                                                       # an empty body is how Yahoo throttles
        elif resp.status_code not in (429, 503):
            raise RuntimeError(f"yahoo {provider_symbol}: http {resp.status_code}")
        if attempt < retries:
            sleep(wait)
            wait = min(wait * 1.6, 120.0)
            continue
        raise RuntimeError(f"yahoo {provider_symbol}: still throttled after {retries} retries")
    raise RuntimeError("unreachable")


def _count(con, symbol: str, timeframe: str) -> int:
    return con.execute("SELECT count(*) FROM bars WHERE venue = 'yahoo' AND symbol = ? AND timeframe = ?", [symbol, timeframe]).fetchone()[0]


def collect(symbols: list[str] | None = None, timeframes: list[str] | None = None, client: httpx.Client | None = None, pause_s: float = PAUSE_S,
            sleep=time.sleep, progress=None) -> tuple[bool, dict]:
    """Fetch closed bars for each symbol and timeframe. One failure does not stop the others. Returns (all ok, rows added per symbol/timeframe)."""
    symbols = symbols or [i.symbol for i in instruments.INSTRUMENTS if i.source == "yahoo"]
    timeframes = timeframes or ["1d", "1h"]
    own = client is None
    client = client or httpx.Client(headers=HEADERS, timeout=40)
    ok, summary, first = True, {}, True
    try:
        for sym in symbols:
            inst = instruments.get(sym)
            if inst is None or inst.source != "yahoo":
                ok = False
                emit("collector.error", service=SERVICE, level="error", symbol=sym, error="not a yahoo instrument")
                continue
            for tf in timeframes:
                interval, _length, first_range, update_range = INTERVALS[tf]
                with connect() as con:
                    have = _count(con, sym, tf)
                if not first:
                    sleep(pause_s)
                first = False
                try:
                    payload = fetch(client, inst.provider_symbol, interval, update_range if have else first_range, sleep=sleep)
                    now = utcnow()
                    bars = parse_chart(payload, inst, tf, now, now)
                    with connect() as con:
                        before = _count(con, sym, tf)
                        con.executemany("INSERT OR IGNORE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", bars)
                        summary[f"{sym}/{tf}"] = _count(con, sym, tf) - before
                except Exception as exc:
                    ok = False
                    emit("collector.error", service=SERVICE, level="error", symbol=sym, timeframe=tf, error=repr(exc)[:300])
                if progress:
                    progress(sym, tf, summary.get(f"{sym}/{tf}"))
    finally:
        if own:
            client.close()
    emit("collector.run", service=SERVICE, ok=ok, timeframe=",".join(timeframes), rows_added=summary)
    return ok, summary
