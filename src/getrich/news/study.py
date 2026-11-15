"""Exploratory event study: do the daily news features line up with forward returns at all?

For every news feature, symbol and horizon: Spearman rank IC between the feature on day t (known at that day's close) and
the log return from that close to the close h days later, with a moving-block-bootstrap interval (the blocks keep the
autocorrelation that overlapping returns create). 16 features x 2 symbols x 3 horizons = 96 tests, so about 5 are
"significant" by chance alone: the report says how many were found against how many chance predicts, and nothing here is
a trading claim. The pre-registered experiment is the confirmatory test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..eval.data import load_bars
from ..forecast.evaluate import block_bootstrap_ic

HORIZONS = (1, 5, 20)


def forward_log_returns(close: pd.Series, h: int) -> pd.Series:
    return np.log(close.shift(-h) / close)


def study_frame(feats: pd.DataFrame, close: pd.Series, h: int, symbol: str, reps: int = 400) -> list[dict]:
    y = forward_log_returns(close, h)
    rows = []
    for col in feats.columns:
        d = pd.concat([feats[col], y], axis=1, join="inner").dropna()
        if len(d) < 60 or d.iloc[:, 0].nunique() < 3:
            rows.append({"feature": col, "symbol": symbol, "h": h, "n": len(d), "ic": float("nan"), "lo": float("nan"), "hi": float("nan"), "significant": False})
            continue
        x, v = d.iloc[:, 0].to_numpy(), d.iloc[:, 1].to_numpy()
        ic = float(spearmanr(x, v).statistic)
        lo, hi = block_bootstrap_ic(x, v, block=max(2 * h, 10), reps=reps)
        rows.append({"feature": col, "symbol": symbol, "h": h, "n": len(d), "ic": ic, "lo": lo, "hi": hi, "significant": bool(lo > 0 or hi < 0)})
    return rows


def run(symbols=("BTCUSDT", "ETHUSDT"), horizons=HORIZONS, reps: int = 400) -> dict:
    from ..eval.features import news_frame

    feats = news_frame("gdelt")
    rows = []
    for s in symbols:
        close = load_bars(s, "1d")["close"]
        close.index = close.index.normalize()
        f = feats.copy()
        f.index = f.index.normalize()
        for h in horizons:
            rows += study_frame(f, close, h, s, reps)
    tested = [r for r in rows if r["ic"] == r["ic"]]
    nsig = sum(r["significant"] for r in tested)
    return {"rows": rows, "tested": len(tested), "significant": nsig, "expected_by_chance": 0.05 * len(tested),
            "from": str(feats.index.min().date()), "to": str(feats.index.max().date())}


def to_markdown(res: dict) -> str:
    rows = res["rows"]
    L = ["# News features versus forward returns (exploratory event study)", "",
         f"GDELT daily features {res['from']} to {res['to']}. {res['tested']} tests (feature x symbol x horizon); {res['significant']} have a 95% block-bootstrap "
         f"interval that excludes zero, against about {res['expected_by_chance']:.1f} expected by chance alone. This is exploratory and not a trading claim; "
         "the pre-registered experiment is the confirmatory test.", ""]
    L += ["| feature | symbol | horizon | n | rank IC | 95% interval | excludes 0 |", "|---|---|---:|---:|---:|---|---|"]
    for r in sorted(rows, key=lambda r: -abs(r["ic"]) if r["ic"] == r["ic"] else 0)[:25]:
        L.append(f"| {r['feature']} | {r['symbol']} | {r['h']}d | {r['n']} | {r['ic']:+.3f} | {r['lo']:+.3f} to {r['hi']:+.3f} | {'yes' if r['significant'] else 'no'} |")
    L += ["", "Top 25 by absolute IC shown; the full set is what the count above is taken over.", ""]
    return "\n".join(L)
