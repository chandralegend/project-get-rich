"""Baseline strategies every later model has to beat.

All signals use data up to and including day t only (causal). Positions are fractions of equity for a
spot, long-only account: 0 = flat, 1 = fully invested, never leveraged.

  buy_and_hold   position 1 from the start
  trend_signal   long/flat: the average of "fast EMA above slow EMA" over several lookback pairs
  vol_scaled     trend_signal * min(1, target_vol / forecast_vol)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_PAIRS = ((16, 64), (32, 128), (64, 256))
DAYS = 365


def buy_and_hold(index: pd.Index) -> pd.Series:
    return pd.Series(1.0, index=index)


def ewma_vol(close: pd.Series, lam: float = 0.94) -> pd.Series:
    """RiskMetrics-style annualised volatility forecast for the next day, from past daily returns."""
    r2 = close.pct_change() ** 2
    var = r2.ewm(alpha=1 - lam, adjust=False, min_periods=20).mean()
    return np.sqrt(var * DAYS)


def trend_signal(close: pd.Series, pairs=DEFAULT_PAIRS) -> pd.Series:
    votes = []
    for fast, slow in pairs:
        ema_f = close.ewm(span=fast, adjust=False, min_periods=slow).mean()
        ema_s = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
        votes.append((ema_f > ema_s).astype(float).where(ema_s.notna(), 0.0))
    return sum(votes) / len(votes)


def vol_scaled(signal: pd.Series, vol_annual: pd.Series, target_vol: float = 0.20, max_leverage: float = 1.0) -> pd.Series:
    scale = (target_vol / vol_annual).clip(upper=max_leverage)
    return (signal * scale).fillna(0.0).clip(0.0, max_leverage)
