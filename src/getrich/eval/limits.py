"""Derive risk limits from data, not from taste (Phase 1 task: "derive drawdown and loss limits").

For each exposure profile (the largest fraction of equity allowed in crypto at once) this module reports:
  * the distribution of one-year maximum drawdown for the baseline trend strategy, from a stationary
    bootstrap of its historical daily net returns,
  * daily-loss quantiles,
  * the loss from the worst historical 24-hour fall in each asset, with a 1.5x margin because history is
    not a bound on the future,
and from those PROPOSES halts. The proposals are rules applied to the numbers, not predictions. Every
statistic here describes 2021 to 2026 BTC and ETH; a worse path than any in the sample can happen.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .data import load_bars

PROFILES = {"minimal": 0.20, "conservative": 0.25, "moderate": 0.50, "full": 1.00}
SAFETY_MARGIN = 1.5
DD_PERCENTILE = 95
DAILY_HALT_QUANTILE = 0.001   # a day worse than 99.9% of historical days stops trading
YEAR = 365


def ceil_to(x: float, step: float) -> float:
    return round(math.ceil(round(x / step, 9)) * step, 9)


def stationary_bootstrap(returns: np.ndarray, n_paths: int = 5000, horizon: int = YEAR, mean_block: int = 20, seed: int = 0) -> np.ndarray:
    """Resample a return series in random-length blocks (mean `mean_block`), keeping its serial structure."""
    rng = np.random.default_rng(seed)
    n = len(returns)
    jump = rng.random((n_paths, horizon)) < 1.0 / mean_block
    jump[:, 0] = True
    fresh = rng.integers(0, n, size=(n_paths, horizon))
    idx = np.empty((n_paths, horizon), dtype=int)
    idx[:, 0] = fresh[:, 0]
    for t in range(1, horizon):
        idx[:, t] = np.where(jump[:, t], fresh[:, t], (idx[:, t - 1] + 1) % n)
    return returns[idx]


def max_drawdowns(paths: np.ndarray) -> np.ndarray:
    eq = np.cumprod(1.0 + paths, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.ones((len(paths), 1)), eq], axis=1), axis=1)[:, 1:]
    return (1.0 - eq / peak).max(axis=1)


def worst_rolling_drop(close: pd.Series, window_hours: int = 24) -> tuple[float, pd.Timestamp]:
    """Largest fall over any `window_hours` of hourly closes, as a positive fraction, and when it ended."""
    ret = close / close.shift(window_hours) - 1.0
    ret = ret.dropna()
    return float(-ret.min()), ret.idxmin()


def worst_events(close: pd.Series, window_hours: int = 24, n: int = 5, separation_days: int = 3) -> list[tuple[pd.Timestamp, float]]:
    ret = (close / close.shift(window_hours) - 1.0).dropna().sort_values()
    picked: list[tuple[pd.Timestamp, float]] = []
    for ts, val in ret.items():
        if all(abs((ts - p).total_seconds()) > separation_days * 86400 for p, _ in picked):
            picked.append((ts, float(-val)))
        if len(picked) == n:
            break
    return picked


def derive(trend_returns: pd.DataFrame, hourly_closes: dict[str, pd.Series], seed: int = 0) -> dict:
    """trend_returns: net daily returns of the trend strategy per asset (columns), common dates."""
    port = trend_returns.mean(axis=1)                      # equal-weight sleeves
    base = port.to_numpy()
    worst24 = {s: worst_rolling_drop(c) for s, c in hourly_closes.items()}
    worst_move = max(v for v, _ in worst24.values())
    profiles = {}
    for name, cap in PROFILES.items():
        r = cap * base
        dd = max_drawdowns(stationary_bootstrap(r, seed=seed))
        pct = {p: float(np.percentile(dd, p)) for p in (50, 90, 95, 99)}
        loss_q = float(-np.quantile(r, DAILY_HALT_QUANTILE))
        event = cap * worst_move * SAFETY_MARGIN
        profiles[name] = {
            "exposure_cap": cap,
            "historical_max_drawdown": float(max_drawdowns(r[None, :])[0]),
            "bootstrap_1y_max_drawdown": pct,
            "daily_loss_p99_9": loss_q,
            "worst_day": float(-r.min()),
            "worst_24h_event_loss_x1_5": event,
            "proposed_account_drawdown_halt": ceil_to(pct[DD_PERCENTILE], 0.05),
            "proposed_daily_loss_halt": ceil_to(max(loss_q, 0.0025), 0.005),
        }
        # A halt cannot stop a gap. The profile is only coherent if a repeat of the worst historical
        # 24-hour fall (with the safety margin) still fits inside the drawdown halt.
        profiles[name]["gap_fits_inside_halt"] = event <= profiles[name]["proposed_account_drawdown_halt"] + 1e-9
    coherent = [n for n, p in profiles.items() if p["gap_fits_inside_halt"]]
    recommended = max(coherent, key=lambda n: profiles[n]["exposure_cap"]) if coherent else min(profiles, key=lambda n: profiles[n]["exposure_cap"])
    return {"profiles": profiles, "recommended": recommended, "worst24": {s: (v, ts) for s, (v, ts) in worst24.items()},
            "events": {s: worst_events(c) for s, c in hourly_closes.items()}, "worst_move": worst_move,
            "sample_days": len(base), "start": str(port.index[0].date()), "end": str(port.index[-1].date())}


def load_hourly(symbols) -> dict[str, pd.Series]:
    return {s: load_bars(s, "1h")["close"] for s in symbols}


def to_markdown(res: dict, recommended: str | None = None) -> str:
    recommended = recommended or res["recommended"]
    P = res["profiles"]
    pct = lambda x, nd=1: f"{x * 100:.{nd}f}%"
    L = [
        "# Risk limits proposal (for your approval)",
        "",
        f"Derived on {res['sample_days']} days of baseline trend-strategy returns ({res['start']} to {res['end']}), equal-weight BTC and ETH sleeves, "
        f"net of assumed costs. These are rules applied to historical numbers. History is one crypto cycle: a worse path is possible, so treat every number as a floor on risk, not a ceiling.",
        "",
        "## How each number is derived",
        "",
        f"- **Exposure cap**: the largest fraction of equity in crypto at once. It is the main risk knob, because a spot long-only account has no way to cut a position during a gap.",
        f"- **Account drawdown halt**: the {DD_PERCENTILE}th percentile of simulated one-year maximum drawdown (stationary bootstrap, 5,000 paths, 20-day average block), rounded up to the next 5%. Normal variance should rarely hit it.",
        f"- **Daily loss halt**: the loss of a day worse than {100 * (1 - DAILY_HALT_QUANTILE):.1f}% of historical days, rounded up to the next 0.5% (minimum 0.25%).",
        f"- **Worst 24-hour event**: the largest 24-hour fall in either asset ({', '.join(f'{s} {pct(v)} ending {ts:%Y-%m-%d}' for s, (v, ts) in res['worst24'].items())}), times a {SAFETY_MARGIN}x margin, times the exposure cap. This is what one gap does to the account.",
        "",
        "## Profiles",
        "",
        "| | " + " | ".join(P) + " |",
        "|---|" + "---:|" * len(P),
    ]
    rows = [
        ("Exposure cap (share of equity in crypto)", lambda p: pct(p["exposure_cap"], 0)),
        ("Historical max drawdown, this strategy", lambda p: pct(p["historical_max_drawdown"])),
        ("1-year max drawdown, median", lambda p: pct(p["bootstrap_1y_max_drawdown"][50])),
        ("1-year max drawdown, 90th percentile", lambda p: pct(p["bootstrap_1y_max_drawdown"][90])),
        ("1-year max drawdown, 95th percentile", lambda p: pct(p["bootstrap_1y_max_drawdown"][95])),
        ("1-year max drawdown, 99th percentile", lambda p: pct(p["bootstrap_1y_max_drawdown"][99])),
        ("Worst historical day", lambda p: pct(p["worst_day"], 2)),
        ("Daily loss at the 99.9th percentile", lambda p: pct(p["daily_loss_p99_9"], 2)),
        ("Loss from worst 24-hour fall x 1.5", lambda p: pct(p["worst_24h_event_loss_x1_5"])),
        ("**Proposed account drawdown halt**", lambda p: f"**{pct(p['proposed_account_drawdown_halt'], 0)}**"),
        ("Does a repeat of the worst 24-hour fall (x1.5) fit inside that halt?", lambda p: "yes" if p["gap_fits_inside_halt"] else "**no**"),
        ("**Proposed daily loss halt**", lambda p: f"**{pct(p['proposed_daily_loss_halt'], 1)}**"),
    ]
    for label, f in rows:
        L.append(f"| {label} | " + " | ".join(f(p) for p in P.values()) + " |")
    L += ["", "## Worst 24-hour falls in the data (hourly closes)", "", "| Asset | Date (UTC) | Fall |", "|---|---|---:|"]
    for s, evs in res["events"].items():
        for ts, v in evs:
            L.append(f"| {s} | {ts:%Y-%m-%d %H:%M} | {pct(v)} |")
    rec = P[recommended]
    L += ["", f"## Recommended starting profile: {recommended}", "",
          f"Exposure cap {pct(rec['exposure_cap'], 0)}, account drawdown halt {pct(rec['proposed_account_drawdown_halt'], 0)}, daily loss halt {pct(rec['proposed_daily_loss_halt'], 1)}. ",
          "The rule: pick the largest profile whose worst-24-hour-fall loss (with margin) still fits inside its own drawdown halt. A halt cannot stop a gap, "
          "so a profile where one gap breaks the halt is not coherent, whatever its average behaviour. "
          "Nothing yet shows the system has an edge, so the profile can only be raised later by a written rule after live results exist. "
          "This is a research recommendation, not personal financial advice. Which profile you accept is your decision.", ""]
    return "\n".join(L)


def to_toml(res: dict, profile: str, approved: bool = False, risk_per_trade: float | None = None, max_leverage: float | None = None,
            allow_short: bool = False, max_exposure_fraction: float | None = None) -> str:
    p = res["profiles"][profile]
    header = (
        "# APPROVED by the owner. The Phase 4 risk gate will load and hash-pin this file. Change it only by approving again.\n"
        if approved
        else "# PROPOSED risk limits. Not active. Becomes limits.toml only when the owner approves it.\n"
    )
    return (
        header +
        f"profile = \"{profile}\"\n"
        f"max_exposure_fraction = {max_exposure_fraction if max_exposure_fraction is not None else p['exposure_cap']}\n"
        f"account_drawdown_halt = {p['proposed_account_drawdown_halt']:.2f}\n"
        f"daily_loss_halt = {p['proposed_daily_loss_halt']:.3f}\n"
        + (f"risk_per_trade = {risk_per_trade}\n" if risk_per_trade is not None else "")
        + (f"max_leverage = {max_leverage}\n" if max_leverage is not None else "")
        + ("allow_short = true\n" if allow_short else "") +
        f"derived_from_days = {res['sample_days']}\n"
        f"derived_from_range = \"{res['start']} to {res['end']}\"\n"
    )
