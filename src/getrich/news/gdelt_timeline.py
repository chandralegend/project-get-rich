"""Daily GDELT news series (volume and tone) per topic: fetch once, cache the raw answers, build causal features.

Series are fixed in advance (they are part of docs/preregistration-news-forecast.md) so no one can pick the ones that happened to
work. The query text, the requests and the answers are all kept on disk under data/news/gdelt_timeline so the data can be audited.

Timing: a daily point is the whole UTC day t. The PI-Net decides at the close of the daily bar for day t (00:00 UTC of t+1), so a
feature built from day t's point is known at decision time. Features use only trailing windows ending at t.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from .. import config
from ..obs.events import emit

API = "https://api.gdeltproject.org/api/v2/doc/doc"
SERVICE = "news.gdelt"
START = "20200101000000"
PAUSE_S = 25.0                          # GDELT asks for patience; a burst earlier got this connection throttled
MODES = {"vol": "timelinevol", "tone": "timelinetone"}
WINDOW = 90                             # trailing days for the z-scores
MAX_FFILL_DAYS = 7                      # a day GDELT is missing is filled from the last known value for at most a week

SERIES: dict[str, str] = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "crypto": "(cryptocurrency OR crypto OR stablecoin)",
    "hack": "(hack OR hacked OR exploit OR stolen OR bankruptcy OR collapse) (crypto OR bitcoin OR binance OR coinbase)",
    "regulation": "(regulation OR ban OR lawsuit OR crackdown OR sec) (crypto OR bitcoin)",
    "etf": "bitcoin (ETF OR inflows OR outflows)",
    "fed": '("federal reserve" OR fomc OR "rate hike" OR "rate cut")',
    "inflation": "(inflation OR cpi)",
}


def cache_dir() -> Path:
    return config.data_dir() / "news" / "gdelt_timeline"


def cache_path(name: str, mode: str) -> Path:
    return cache_dir() / f"{name}.{mode}.json"


def parse_timeline(payload: dict) -> list[tuple[str, float]]:
    """[(YYYY-MM-DD, value)] from a GDELT timeline answer. Raises if the answer has no series."""
    tl = (payload or {}).get("timeline") or []
    if not tl or not tl[0].get("data"):
        raise ValueError("answer has no timeline data")
    out = []
    for p in tl[0]["data"]:
        d = datetime.strptime(p["date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        out.append((d.strftime("%Y-%m-%d"), float(p["value"])))
    return out


def fetch_one(client: httpx.Client, name: str, mode: str, end: str, *, retries: int = 14, sleep=time.sleep) -> list[tuple[str, float]]:
    """GDELT throttles this connection in bursts (HTTP 429 after a ten second wait). Wait and retry patiently: 90 seconds, growing by half
    each time to a five minute cap, up to `retries` times, which is over an hour in the worst case. Other errors fail at once."""
    params = {"query": f"{SERIES[name]} sourcelang:english", "mode": MODES[mode], "format": "json", "startdatetime": START, "enddatetime": end}
    wait = 90.0
    for attempt in range(retries + 1):
        resp = client.get(API, params=params)
        if resp.status_code == 200:
            try:
                data = parse_timeline(resp.json())
            except ValueError:                                        # GDELT answers a bad or empty query in plain text
                raise RuntimeError(f"gdelt returned no timeline for {name}/{mode}: {resp.text[:120]!r}")
            cache_dir().mkdir(parents=True, exist_ok=True)
            cache_path(name, mode).write_text(json.dumps({"name": name, "mode": mode, "query": SERIES[name], "end": end, "fetched_at": datetime.now(timezone.utc).isoformat(), "data": data}))
            return data
        if resp.status_code in (429, 503) and attempt < retries:
            sleep(wait)
            wait = min(wait * 1.5, 300.0)
            continue
        raise RuntimeError(f"gdelt {name}/{mode}: http {resp.status_code} {resp.text[:100]!r}")
    raise RuntimeError("unreachable")


def fetch_all(*, refresh: bool = False, end: str | None = None, client: httpx.Client | None = None, pause_s: float = PAUSE_S, sleep=time.sleep, progress=None) -> dict:
    """Fetch every series in both modes that is not cached yet (or all, with refresh). Slow on purpose: about a request per 40 seconds."""
    end = end or datetime.now(timezone.utc).strftime("%Y%m%d000000")
    own = client is None
    client = client or httpx.Client(timeout=120, headers={"User-Agent": "getrich-research/0.1"})
    done, skipped, first = 0, 0, True
    try:
        for name in SERIES:
            for mode in MODES:
                if cache_path(name, mode).exists() and not refresh:
                    skipped += 1
                    continue
                if not first:
                    sleep(pause_s)
                first = False
                fetch_one(client, name, mode, end, sleep=sleep)
                done += 1
                if progress:
                    progress(name, mode, done)
    finally:
        if own:
            client.close()
    emit("news.gdelt_fetched", service=SERVICE, fetched=done, cached=skipped)
    return {"fetched": done, "cached": skipped}


def load_daily(end: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Daily frame, one row per UTC day, columns `<series>_vol` and `<series>_tone`. Missing days are filled forward from the past
    for at most MAX_FFILL_DAYS (never from the future); anything still missing stays NaN. Returns (frame, info about gaps)."""
    cols = {}
    for name in SERIES:
        for mode in MODES:
            p = cache_path(name, mode)
            if not p.exists():
                raise RuntimeError(f"no cached GDELT series for {name}/{mode}: run `getrich news-fetch`")
            d = json.loads(p.read_text())["data"]
            cols[f"{name}_{mode}"] = pd.Series({pd.Timestamp(day, tz="UTC"): v for day, v in d})
    raw = pd.DataFrame(cols).sort_index()
    full = pd.date_range(raw.index.min(), raw.index.max(), freq="D", tz="UTC")
    frame = raw.reindex(full)
    missing = int(frame.isna().all(axis=1).sum())
    frame = frame.ffill(limit=MAX_FFILL_DAYS)
    info = {"days": len(full), "days_missing_all_series": missing, "still_missing_after_fill": int(frame.isna().any(axis=1).sum()),
            "from": str(full[0].date()), "to": str(full[-1].date())}
    return frame, info


def news_features(daily: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """Per series: volume z-score and tone z-score against the trailing `window` days ending at the same day (causal).
    Days without enough history, or without data, become 0 (neutral) after the z-score. Column names: news_<series>_vz / _tz."""
    out = {}
    for name in SERIES:
        for mode, tag in (("vol", "vz"), ("tone", "tz")):
            s = daily[f"{name}_{mode}"]
            mu, sd = s.rolling(window, min_periods=30).mean(), s.rolling(window, min_periods=30).std()
            z = (s - mu) / sd.replace(0, np.nan)
            out[f"news_{name}_{tag}"] = z.clip(-5, 5).fillna(0.0)
    return pd.DataFrame(out, index=daily.index)


FEATURES = [f"news_{n}_{t}" for n in SERIES for t in ("vz", "tz")]
