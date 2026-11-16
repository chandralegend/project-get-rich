"""Daily live forecasts: the newest closed daily bar gets a forecast from each model, for BTC and ETH.

The walk-forward caches (generate.py) were built on the host for the research. This keeps them current: one new origin per model and symbol, the
day after a daily bar closes. It runs in the models container (torch and the model weights live only there), never in the trading path.

Safety: weights are checked against the lock (sha256) before any worker runs, and Kronos's reviewed source files are checked byte for byte. A
model or symbol that fails is reported and does not stop the others; nothing here can place an order or call the network.
Limits, stated honestly: the cache history of Kronos was generated every 5th day on the Mac's GPU; new origins are daily and drawn on CPU, so its
newest numbers are a different sample than a Mac run would give. Chronos-2 and TimesFM are deterministic and were checked to match the Mac exactly
(docs/models-container-spike.md).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..eval.data import load_bars
from ..obs.events import emit
from . import fetch, generate, models
from .base import load_cache

SERVICE = "forecast.live"
MODELS = ("chronos2", "timesfm25", "kronos_small")
SYMBOLS = ("BTCUSDT", "ETHUSDT")


def _has_origin(cache, origin: pd.Timestamp) -> bool:
    ns = np.datetime64(origin.tz_convert("UTC").tz_localize(None), "ns")
    pool = list(cache.origins) + list(cache.skipped if cache.skipped is not None else [])
    return any(np.datetime64(o, "ns") == ns for o in pool)


def run(names: tuple[str, ...] = MODELS, symbols: tuple[str, ...] = SYMBOLS, forecaster=None) -> dict:
    """`forecaster(name)` lets tests supply a stand-in; the real one is the isolated subprocess worker."""
    results, bars = [], {s: load_bars(s, "1d") for s in symbols}          # bars are read once, with no database lock held while a model runs
    for name in names:
        problems = fetch.verify(name) + (fetch.verify_code() if name.startswith("kronos") else [])
        if problems:
            results += [{"model": name, "symbol": s, "status": "refused", "error": "; ".join(problems)[:300]} for s in symbols]
            emit("forecast.live_refused", service=SERVICE, level="error", model=name, problems=problems[:3])
            continue
        fc = None
        for sym in symbols:
            newest = bars[sym].index[-1]
            cache = load_cache(name, sym)
            if cache is not None and _has_origin(cache, newest):
                results.append({"model": name, "symbol": sym, "status": "up_to_date", "origin": str(newest.date())})
                continue
            try:
                fc = fc or (forecaster(name) if forecaster else models.get(name))
                generate.generate(fc, sym, bars[sym], stride=1, since=newest)         # stride 1 and `since` the newest bar: exactly one new origin
                done = load_cache(name, sym)
                ok = done is not None and _has_origin(done, newest)
                results.append({"model": name, "symbol": sym, "status": "new" if ok else "failed", "origin": str(newest.date()), **({} if ok else {"error": "no forecast was written"})})
            except Exception as exc:                                            # one failing model or symbol must not stop the rest
                results.append({"model": name, "symbol": sym, "status": "failed", "origin": str(newest.date()), "error": f"{type(exc).__name__}: {str(exc)[:240]}"})
    failed = [r for r in results if r["status"] in ("failed", "refused")]
    emit("forecast.live_run", service=SERVICE, level="warn" if failed else "info", new=sum(r["status"] == "new" for r in results), failed=len(failed))
    return {"ok": not failed, "results": results}


def status(symbols: tuple[str, ...] = SYMBOLS, names: tuple[str, ...] = MODELS) -> list[dict]:
    """Newest cached origin per model and symbol, and its age against the newest daily bar. Read-only; used by the UI and the packet."""
    out = []
    for sym in symbols:
        try:
            newest = load_bars(sym, "1d").index[-1]
        except Exception:
            newest = None
        for name in names:
            try:
                c = load_cache(name, sym)
            except Exception as exc:
                out.append({"model": name, "symbol": sym, "error": type(exc).__name__})
                continue
            if c is None or len(c) == 0:
                out.append({"model": name, "symbol": sym, "newest_origin": None, "days_behind": None})
                continue
            o = pd.Timestamp(c.origins.max()).tz_localize("UTC")
            out.append({"model": name, "symbol": sym, "newest_origin": str(o.date()), "days_behind": None if newest is None else int((newest - o).days)})
    return out
