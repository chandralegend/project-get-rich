"""Binance public klines collector (REST, no API key). Daily bars by default.

Only CLOSED bars are stored. Production data comes from the REST API on purpose: the bulk
data.binance.vision files are licensed for personal non-production research only (see ARCHITECTURE.md).
The Binance API terms themselves have not been read yet.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from ..obs.events import emit, utcnow
from ..obs.heartbeat import beat
from ..store.db import connect

SERVICE = "collector.binance"
BASE = "https://api.binance.com"
HEADERS = {"User-Agent": "getrich-research/0.1"}
PAGE = 1000


def parse_klines(rows, symbol: str, timeframe: str, ingested_at: datetime, now_ms: int, venue: str = "binance"):
    """Convert Binance kline rows to bar tuples, dropping any bar that has not closed yet."""
    out = []
    for k in rows:
        if int(k[6]) >= now_ms:
            continue
        out.append(
            (
                venue,
                symbol,
                timeframe,
                datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc),
                float(k[1]),
                float(k[2]),
                float(k[3]),
                float(k[4]),
                float(k[5]),
                float(k[7]),
                int(k[8]),
                ingested_at,
            )
        )
    return out


def _count(con, symbol: str, timeframe: str) -> int:
    return con.execute(
        "SELECT count(*) FROM bars WHERE venue='binance' AND symbol=? AND timeframe=?",
        [symbol, timeframe],
    ).fetchone()[0]


def _collect_symbol(client: httpx.Client, symbol: str, timeframe: str, start: str, sleep: float) -> int:
    with connect() as con:
        last = con.execute(
            "SELECT max(ts_open) FROM bars WHERE venue='binance' AND symbol=? AND timeframe=?",
            [symbol, timeframe],
        ).fetchone()[0]
    if last is not None:
        start_ms = int(last.timestamp() * 1000) + 1
    else:
        start_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)

    added = 0
    while True:
        resp = client.get(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": timeframe, "startTime": start_ms, "limit": PAGE},
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        now = utcnow()
        bars = parse_klines(rows, symbol, timeframe, now, int(now.timestamp() * 1000))
        if bars:
            with connect() as con:
                before = _count(con, symbol, timeframe)
                con.executemany("INSERT OR IGNORE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", bars)
                added += _count(con, symbol, timeframe) - before
        if len(rows) < PAGE:
            break
        start_ms = int(rows[-1][0]) + 1
        time.sleep(sleep)
    return added


def collect(
    symbols: list[str],
    timeframe: str = "1d",
    start: str = "2020-01-01",
    client: httpx.Client | None = None,
    sleep: float = 0.1,
) -> tuple[bool, dict[str, int]]:
    """Collect closed bars for each symbol. One symbol failing does not stop the others."""
    own = client is None
    client = client or httpx.Client(base_url=BASE, headers=HEADERS, timeout=20)
    ok, summary = True, {}
    try:
        for symbol in symbols:
            try:
                summary[symbol] = _collect_symbol(client, symbol, timeframe, start, sleep)
            except Exception as exc:  # network, HTTP status, or parse problems
                ok = False
                emit("collector.error", service=SERVICE, level="error", symbol=symbol, error=repr(exc))
    finally:
        if own:
            client.close()
    emit("collector.run", service=SERVICE, ok=ok, timeframe=timeframe, rows_added=summary)
    beat(SERVICE, ok=ok, rows_added=sum(summary.values()))
    return ok, summary
