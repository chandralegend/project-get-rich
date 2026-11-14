"""HAR-RV volatility forecasting (Corsi), walk-forward and causal.

Realised variance for a day is the sum of squared hourly log returns. The model regresses tomorrow's
log RV on today's log RV and the log of the 5-day and 22-day average RV. It refits on an expanding
window every `refit_every` days using only rows whose targets were already known, so a forecast made
at the close of day t never uses anything after t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DAYS = 365


def daily_rv_from_hourly(hourly: pd.DataFrame) -> pd.Series:
    """Daily realised variance (UTC days). Days without all 24 hourly returns are dropped."""
    lr = np.log(hourly["close"]).diff()
    day = lr.index.floor("D")
    sq = (lr**2).groupby(day)
    rv = sq.sum()
    count = lr.groupby(day).count()
    rv = rv[count == 24]
    rv.index.name = "day"
    return rv[rv > 0]


def _features(rv: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "d": np.log(rv),
            "w": np.log(rv.rolling(5).mean()),
            "m": np.log(rv.rolling(22).mean()),
        }
    )


def har_forecast(rv: pd.Series, min_train: int = 365, refit_every: int = 30) -> pd.Series:
    """Forecast of the NEXT day's realised variance, indexed by the day the forecast is made."""
    x = _features(rv)
    y = np.log(rv).shift(-1)                      # target for the row at day t is log RV of day t+1
    X = np.column_stack([np.ones(len(x)), x.to_numpy()])
    yv = y.to_numpy()
    valid = ~np.isnan(X).any(axis=1)
    out = np.full(len(rv), np.nan)
    beta, resid_var, last_fit = None, 0.0, -10**9
    for t in range(len(rv)):
        if not valid[t]:
            continue
        # rows usable at time t have a known target: s <= t-1
        train = np.where(valid[:t] & ~np.isnan(yv[:t]))[0]
        if len(train) < min_train:
            continue
        if beta is None or t - last_fit >= refit_every:
            beta, *_ = np.linalg.lstsq(X[train], yv[train], rcond=None)
            resid_var = float(np.var(yv[train] - X[train] @ beta, ddof=X.shape[1]))
            last_fit = t
        out[t] = np.exp(X[t] @ beta + 0.5 * resid_var)
    return pd.Series(out, index=rv.index, name="har_var")


def ewma_variance_forecast(daily_close: pd.Series, lam: float = 0.94) -> pd.Series:
    r2 = daily_close.pct_change() ** 2
    return r2.ewm(alpha=1 - lam, adjust=False, min_periods=20).mean()


def qlike(forecast_var: pd.Series, realised_var: pd.Series) -> float:
    """Mean QLIKE loss (lower is better). Both series aligned: forecast made at t scored against RV of t+1."""
    f, a = forecast_var.align(realised_var, join="inner")
    ok = (f > 0) & (a > 0)
    ratio = a[ok] / f[ok]
    return float((ratio - np.log(ratio) - 1.0).mean())
