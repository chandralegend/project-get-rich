"""Performance metrics, including the Probabilistic and Deflated Sharpe Ratios.

The PSR and DSR formulas follow Bailey and Lopez de Prado as I know them (background knowledge). They
have NOT been checked against the papers; tests pin hand-computed values and properties, not paper numbers.
All Sharpe ratios inside PSR and DSR are per-period (not annualised).
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329
DAYS_PER_YEAR = 365  # crypto trades every day


def sharpe(returns, periods_per_year: int = DAYS_PER_YEAR) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 2:
        return float("nan")
    sd = r.std(ddof=1)
    return float("nan") if sd == 0 else float(r.mean() / sd * math.sqrt(periods_per_year))


def sortino(returns, periods_per_year: int = DAYS_PER_YEAR) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    downside = np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)) if len(r) else 0.0
    return float("nan") if downside == 0 else float(r.mean() / downside * math.sqrt(periods_per_year))


def equity_curve(returns, start: float = 1.0) -> np.ndarray:
    return start * np.cumprod(1.0 + np.asarray(returns, dtype=float))


def max_drawdown(returns) -> float:
    """Largest peak-to-trough fall of the compounded equity curve, as a positive fraction."""
    eq = equity_curve(returns)
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    return float(np.max(1.0 - eq / peak))


def cagr(returns, periods_per_year: int = DAYS_PER_YEAR) -> float:
    r = np.asarray(returns, dtype=float)
    if len(r) == 0:
        return float("nan")
    growth = float(np.prod(1.0 + r))
    return float("nan") if growth <= 0 else growth ** (periods_per_year / len(r)) - 1.0


def calmar(returns, periods_per_year: int = DAYS_PER_YEAR) -> float:
    dd = max_drawdown(returns)
    return float("nan") if dd == 0 else cagr(returns, periods_per_year) / dd


def summarize(returns, periods_per_year: int = DAYS_PER_YEAR) -> dict:
    r = np.asarray(returns, dtype=float)
    return {
        "n": int(len(r)),
        "cagr": cagr(r, periods_per_year),
        "vol": float(r.std(ddof=1) * math.sqrt(periods_per_year)) if len(r) > 1 else float("nan"),
        "sharpe": sharpe(r, periods_per_year),
        "sortino": sortino(r, periods_per_year),
        "max_drawdown": max_drawdown(r),
        "calmar": calmar(r, periods_per_year),
        "worst_day": float(r.min()) if len(r) else float("nan"),
    }


def _moments(r: np.ndarray) -> tuple[float, float]:
    """Skewness and (non-excess) kurtosis."""
    m = r.mean()
    sd = r.std(ddof=0)
    if sd == 0:
        return 0.0, 3.0
    z = (r - m) / sd
    return float(np.mean(z**3)), float(np.mean(z**4))


def probabilistic_sharpe(sr: float, sr_benchmark: float, n: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """P(true Sharpe > benchmark), given an observed per-period Sharpe `sr` over `n` observations."""
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if n < 2 or denom <= 0:
        return float("nan")
    return _N.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom))


def expected_max_sharpe(n_trials: int, var_trial_sharpes: float) -> float:
    """Expected best per-period Sharpe among `n_trials` unskilled strategies (the deflation benchmark)."""
    if n_trials <= 1 or var_trial_sharpes <= 0:
        return 0.0
    return math.sqrt(var_trial_sharpes) * (
        (1 - EULER_GAMMA) * _N.inv_cdf(1 - 1.0 / n_trials)
        + EULER_GAMMA * _N.inv_cdf(1 - 1.0 / (n_trials * math.e))
    )


def deflated_sharpe(returns, trial_sharpes) -> float:
    """Probability that the strategy's true Sharpe is positive after accounting for how many variants
    were tried. `trial_sharpes` are the per-period Sharpe ratios of EVERY variant tried, including this one.
    With a single trial this is just the PSR against zero."""
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 3 or r.std(ddof=1) == 0:
        return float("nan")
    sr = float(r.mean() / r.std(ddof=1))
    trials = np.asarray(list(trial_sharpes), dtype=float)
    n_trials = max(len(trials), 1)
    var = float(np.var(trials, ddof=1)) if n_trials > 1 else 0.0
    skew, kurt = _moments(r)
    return probabilistic_sharpe(sr, expected_max_sharpe(n_trials, var), len(r), skew, kurt)
