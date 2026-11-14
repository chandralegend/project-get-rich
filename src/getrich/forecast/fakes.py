"""Deterministic stand-in forecasters, for tests and for sanity-checking the evaluation harness itself."""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from .base import HORIZONS, QUANTILES, Forecaster

Z = norm.ppf(np.array(QUANTILES))


def _logret(ohlcv: np.ndarray) -> np.ndarray:
    return np.diff(np.log(ohlcv[:, :, 3]), axis=1)


class RandomWalk(Forecaster):
    """Zero drift, Gaussian, scale from the trailing 20-day volatility: the benchmark every real forecaster has to beat."""
    name, context_len = "fake_rw", 64

    def forecast(self, ohlcv, ts):
        sd = _logret(ohlcv)[:, -20:].std(axis=1, ddof=1)
        return np.stack([sd[:, None] * np.sqrt(h) * Z[None, :] for h in HORIZONS], axis=1)


class Momentum(Forecaster):
    """Continues the trailing 20-day mean return, with the same Gaussian scale."""
    name, context_len = "fake_momentum", 64

    def __init__(self, strength: float = 1.0):
        self.strength = strength

    def forecast(self, ohlcv, ts):
        r = _logret(ohlcv)
        sd, mu = r[:, -20:].std(axis=1, ddof=1), r[:, -20:].mean(axis=1)
        return np.stack([(self.strength * mu * h)[:, None] + sd[:, None] * np.sqrt(h) * Z[None, :] for h in HORIZONS], axis=1)


class Oracle(Forecaster):
    """Cheats by looking at the future (given the full close series). It exists to prove the evaluation can see real skill."""
    name, context_len = "fake_oracle", 64

    def __init__(self, close_by_day: dict[int, float], days: list[int], noise: float = 0.002):
        self.close, self.days, self.noise = close_by_day, days, noise

    def forecast(self, ohlcv, ts):
        out = np.zeros((len(ohlcv), len(HORIZONS), len(QUANTILES)))
        for n in range(len(ohlcv)):
            d0 = int(ts[n, -1])
            k = self.days.index(d0)
            for j, h in enumerate(HORIZONS):
                real = np.log(self.close[self.days[min(k + h, len(self.days) - 1)]] / self.close[d0])
                out[n, j] = real + self.noise * np.sqrt(h) * Z
        return out
