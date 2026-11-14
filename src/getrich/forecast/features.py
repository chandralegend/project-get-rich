"""Turn cached forecast quantiles into model features, all scaled by the volatility known at the origin (so BTC and ETH are comparable)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import HORIZONS, QUANTILES, Cache

Q = np.array(QUANTILES)


def prob_up(quantile_values: np.ndarray) -> np.ndarray:
    """P(return > 0) by interpolating the forecast quantile function at zero, clipped to the range the quantiles cover."""
    out = np.empty(len(quantile_values))
    for i, qv in enumerate(quantile_values):
        out[i] = 1.0 - np.interp(0.0, qv, Q, left=Q[0], right=Q[-1])
    return out


def foundation_features(cache: Cache, daily_sigma: pd.Series, prefix: str) -> pd.DataFrame:
    """One row per cached origin, indexed by the origin bar-open time. sigma is the 20-day EWMA daily volatility at the origin."""
    idx = pd.DatetimeIndex(cache.origins).tz_localize("UTC")
    sigma = daily_sigma.reindex(idx).to_numpy()
    f = pd.DataFrame(index=idx)
    q50 = int(np.argmin(np.abs(Q - 0.5)))
    for j, h in enumerate(HORIZONS):
        sd = sigma * np.sqrt(h)
        f[f"{prefix}_med_h{h}"] = cache.cube[:, j, q50] / sd
        f[f"{prefix}_pup_h{h}"] = prob_up(cache.cube[:, j, :]) - 0.5
        if h > 1:
            lo, hi = cache.cube[:, j, 0], cache.cube[:, j, -1]
            f[f"{prefix}_width_h{h}"] = (hi - lo) / sd
            f[f"{prefix}_skew_h{h}"] = ((hi - cache.cube[:, j, q50]) - (cache.cube[:, j, q50] - lo)) / np.where(hi > lo, hi - lo, np.nan)
    return f.replace([np.inf, -np.inf], np.nan)
