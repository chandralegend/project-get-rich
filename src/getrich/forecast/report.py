"""Evaluate every model that has cached forecasts and write a plain report."""

from __future__ import annotations

import pandas as pd

from ..eval.data import load_bars
from . import evaluate as ev
from .base import load_cache
from .models import SPECS

SYMBOLS = ("BTCUSDT", "ETHUSDT")


def run_all(models: list[str] | None = None) -> dict:
    bars = {s: load_bars(s, "1d") for s in SYMBOLS}
    out = {}
    for name in models or sorted(SPECS):
        caches = {s: load_cache(name, s) for s in SYMBOLS}
        if not any(c is not None and len(c) for c in caches.values()):
            continue
        res = ev.evaluate_model(caches, bars, pd.Timestamp(SPECS[name].release, tz="UTC"))
        out[name] = {"table": res, "verdict": ev.verdict(res), "n_origins": {s: (len(c) if c else 0) for s, c in caches.items()}}
    return out


def to_markdown(out: dict) -> str:
    L = ["# Foundation forecaster evaluation", "",
         "Each model forecasts BTC and ETH cumulative log returns at 1, 5 and 20 days from every origin day, using only data up to that day. "
         "Scores are against a zero-drift random walk with the same volatility scale (positive skill = better than the random walk). "
         "`post_release` keeps origins on or after the model's public release date, which it cannot have seen in pretraining; `all` is the full history, "
         "where contamination could only inflate results. See `src/getrich/forecast/evaluate.py` for definitions.", ""]
    if not out:
        return "\n".join(L + ["No cached forecasts yet. Run `getrich forecast-run <model>` after `forecast-fetch`."]) + "\n"
    for name, d in out.items():
        t = d["table"]
        L += [f"## {name}", "", f"**Verdict: {d['verdict']}.** Origins cached: " + ", ".join(f"{s} {n}" for s, n in d["n_origins"].items()) + ".", "",
              "| Window | h | n | Skill | Location skill | IC (95% CI) | Hit / up rate | Cover 80% / 40% | DM p |", "|---|---:|---:|---:|---:|---|---|---|---:|"]
        for _, r in t.iterrows():
            if "skill" not in r or pd.isna(r.get("skill")):
                L.append(f"| {r['window']} | {r['h']} | {r['n']} | not enough data | | | | | |")
                continue
            L.append(f"| {r['window']} | {r['h']} | {r['n']} | {r['skill']:+.3f} | {r['location_skill']:+.3f} | {r['ic']:+.3f} ({r['ic_lo']:+.2f}, {r['ic_hi']:+.2f}) | "
                     f"{r['hit']:.1%} / {r['up_rate']:.1%} | {r['cov80']:.0%} / {r['cov40']:.0%} | {r['dm_p']:.3f} |")
        L.append("")
    L += ["## How to read this", "",
          "- Skill and IC near zero, or intervals that straddle zero, mean no demonstrated edge. Coverage far from 80% / 40% means the model's uncertainty is wrong and it would need recalibration before use.",
          "- Overlapping horizons make daily origins strongly dependent, so the effective sample is roughly n / h. The post-release window is short; a null result there is weak evidence of no skill, a positive one needs forward confirmation.",
          "- A model is only wired into a trading model if it shows skill here on post-release data."]
    return "\n".join(L) + "\n"
