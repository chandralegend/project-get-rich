"""Triple-barrier labels with transaction costs (ARCHITECTURE.md 4.3).

A decision is taken at the CLOSE of bar i and enters at that close. The trade ends at whichever comes first:
  take-profit  at +tp_mult * sigma   (sigma = recent daily volatility as a fraction of price)
  stop-loss    at -sl_mult * sigma
  timeout      at the close of bar i + horizon
Barriers are checked against each following bar's high and low. If one bar touches BOTH barriers we assume
the stop was hit first (conservative, because daily bars hide the intraday order). Fills happen exactly at
the barrier price; slippage is part of the cost model.

Outcomes are in R, where 1R is the stop distance: R_gross = return / stop_fraction and
R_net = R_gross - cost_in_r. A stop-out is therefore -1 - cost, a take-profit is b - cost where
b = tp_mult / sl_mult. Samples whose horizon runs past the end of the data are dropped, never guessed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import CostModel

EPS = 1e-9


def daily_vol(close: pd.Series, span: int = 20) -> pd.Series:
    """EWMA standard deviation of daily returns, using only data up to each day."""
    return close.pct_change().ewm(span=span, min_periods=span).std()


def triple_barrier(
    bars: pd.DataFrame,
    sigma: pd.Series,
    *,
    side: int = 1,
    tp_mult: float = 2.0,
    sl_mult: float = 1.0,
    horizon: int = 10,
    cost: CostModel | None = None,
    bar: pd.Timedelta = pd.Timedelta(days=1),
) -> pd.DataFrame:
    if side not in (1, -1):
        raise ValueError("side must be +1 or -1")
    cost = cost or CostModel()
    idx = bars.index
    high, low, close = bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy()
    sig = sigma.reindex(idx).to_numpy()
    n = len(bars)
    rows = []
    for i in range(n - 1):
        s = sig[i]
        if not np.isfinite(s) or s <= 0:
            continue
        last = i + horizon
        if last > n - 1:
            break  # unresolved from here on
        entry = close[i]
        stop, tp = sl_mult * s, tp_mult * s
        sl_px = entry * (1 - stop) if side == 1 else entry * (1 + stop)
        tp_px = entry * (1 + tp) if side == 1 else entry * (1 - tp)
        exit_j, exit_px, kind = last, close[last], "timeout"
        for j in range(i + 1, last + 1):
            # EPS: 100 * (1 + 0.1) is 110.00000000000001 in floating point, so an exact touch must still count
            if side == 1:
                hit_sl, hit_tp = low[j] <= sl_px * (1 + EPS), high[j] >= tp_px * (1 - EPS)
            else:
                hit_sl, hit_tp = high[j] >= sl_px * (1 - EPS), low[j] <= tp_px * (1 + EPS)
            if hit_sl:
                exit_j, exit_px, kind = j, sl_px, "sl"
                break
            if hit_tp:
                exit_j, exit_px, kind = j, tp_px, "tp"
                break
        ret = side * (exit_px / entry - 1.0)
        r_gross = ret / stop
        cost_r = cost.cost_in_r(stop)
        rows.append(
            {
                "t0": idx[i] + bar,
                "t1": idx[exit_j] + bar,
                "side": side,
                "entry": entry,
                "stop_frac": stop,
                "tp_frac": tp,
                "exit": kind,
                "bars_held": exit_j - i,
                "ret_gross": ret,
                "r_gross": r_gross,
                "cost_r": cost_r,
                "r_net": r_gross - cost_r,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["label"] = (out["r_net"] > 0).astype(int)
    return out
