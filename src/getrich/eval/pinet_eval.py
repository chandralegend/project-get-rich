"""Judge PI-Net models at the strategy level, against the baselines, at base and 2x costs.

Mapping from model output to a strategy: hold the asset long while the model's expected net R is positive,
otherwise hold cash; each asset is an equal-weight sleeve; trades pay the cost model with a 10% no-trade
band. This is a simplification of the triple-barrier trade (which exits at barriers), chosen so the model
and the trend baseline are compared in the same units and by the same backtest engine.

Each CPCV path is a complete out-of-sample prediction series, so every model gets a DISTRIBUTION of
strategy results (one per path), not a single lucky number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import backtest, baselines, metrics
from .costs import CostModel
from .features import Dataset
from .pinet import trade_score

BAND = 0.10


def _window(ds: Dataset) -> tuple[pd.Timestamp, pd.Timestamp]:
    return ds.bar.min(), ds.bar.max()


def model_returns(ds: Dataset, pred: np.ndarray, closes: dict[str, pd.Series], cost: CostModel) -> pd.Series:
    start, end = _window(ds)
    sleeves = []
    for sym in sorted(set(ds.asset)):
        m = ds.asset == sym
        pos = pd.Series((pred[m, 1] > 0).astype(float), index=ds.bar[m])
        close = closes[sym].loc[start:end]
        target = pos.reindex(close.index).fillna(0.0)
        sleeves.append(backtest.run(close, target, cost, BAND)["net"])
    return pd.concat(sleeves, axis=1).mean(axis=1)


def baseline_returns(ds: Dataset, closes: dict[str, pd.Series], cost: CostModel) -> dict[str, pd.Series]:
    start, end = _window(ds)
    out = {}
    for name in ("buy_and_hold", "trend"):
        sleeves = []
        for sym in sorted(set(ds.asset)):
            full = closes[sym]
            pos = baselines.buy_and_hold(full.index) if name == "buy_and_hold" else baselines.trend_signal(full)
            sleeves.append(backtest.run(full.loc[start:end], pos.loc[start:end], cost, BAND)["net"])
        out[name] = pd.concat(sleeves, axis=1).mean(axis=1)
    return out


def evaluate_model(name: str, paths: list[np.ndarray], ds: Dataset, closes: dict[str, pd.Series], cost: CostModel) -> dict:
    stressed = cost.stressed(2.0)
    per_path = []
    for pred in paths:
        base, hard = model_returns(ds, pred, closes, cost), model_returns(ds, pred, closes, stressed)
        per_path.append({
            "sharpe": metrics.sharpe(base), "sharpe_2x": metrics.sharpe(hard), "cagr": metrics.cagr(base),
            "max_dd": metrics.max_drawdown(base), "exposure": float((pred[:, 1] > 0).mean()),
            "trade_score": trade_score(pred, ds.r_net), "trade_score_2x": trade_score(pred, ds.r_at(2.0)),
            "returns": base, "sharpe_period": float(base.mean() / base.std(ddof=1)),
        })
    return {"name": name, "paths": per_path}


def summarize(results: list[dict], baseline: dict[str, pd.Series], baseline_2x: dict[str, pd.Series] | None = None,
              trial_sharpes: list[float] | None = None) -> dict:
    """Adds baseline rows and the Deflated Sharpe, counting every model and baseline as a trial."""
    if trial_sharpes is None:
        trial_sharpes = [float(np.mean([p["sharpe_period"] for p in r["paths"]])) for r in results]
        trial_sharpes += [float(s.mean() / s.std(ddof=1)) for s in baseline.values()]
    rows = []
    for r in results:
        ps = r["paths"]
        dsr = [metrics.deflated_sharpe(p["returns"], trial_sharpes) for p in ps]
        rows.append({
            "name": r["name"], "n_paths": len(ps),
            "sharpe_mean": float(np.mean([p["sharpe"] for p in ps])),
            "sharpe_min": float(np.min([p["sharpe"] for p in ps])), "sharpe_max": float(np.max([p["sharpe"] for p in ps])),
            "sharpe_2x_mean": float(np.mean([p["sharpe_2x"] for p in ps])),
            "cagr_mean": float(np.mean([p["cagr"] for p in ps])), "max_dd_mean": float(np.mean([p["max_dd"] for p in ps])),
            "exposure": float(np.mean([p["exposure"] for p in ps])),
            "trade_score_mean": float(np.mean([p["trade_score"] for p in ps])),
            "trade_score_2x_mean": float(np.mean([p["trade_score_2x"] for p in ps])),
            "dsr_mean": float(np.nanmean(dsr)), "n_trials": len(trial_sharpes),
        })
    base_rows = []
    for name, s in baseline.items():
        base_rows.append({"name": name, "sharpe": metrics.sharpe(s), "cagr": metrics.cagr(s), "max_dd": metrics.max_drawdown(s),
                          "sharpe_2x": metrics.sharpe(baseline_2x[name]) if baseline_2x else float("nan"),
                          "dsr": metrics.deflated_sharpe(s, trial_sharpes), "days": len(s)})
    return {"models": rows, "baselines": base_rows, "n_trials": len(trial_sharpes)}
