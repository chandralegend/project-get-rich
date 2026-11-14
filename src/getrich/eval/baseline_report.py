"""Run the baseline strategies on the stored BTCUSDT and ETHUSDT data and report them honestly.

Strategies (all spot, long-only, never leveraged; positions decided at the close, held over the next day):
  buy_and_hold   always fully invested
  trend          long/flat: average of three EMA-crossover votes (16/64, 32/128, 64/256)
  trend_ewma     trend, scaled to a 20% volatility target using an EWMA volatility forecast
  trend_har      trend, scaled to the same target using a HAR-RV volatility forecast

All parameters were fixed before running, from common defaults, and none was tuned on these results.
Every strategy-and-asset combination run here counts as one trial for the Deflated Sharpe Ratio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import backtest, baselines, har, metrics
from .costs import CostModel
from .data import load_bars
from ..obs.events import emit

STRATEGIES = ("buy_and_hold", "trend", "trend_ewma", "trend_har")
TARGET_VOL = 0.20
BAND = 0.10


def _positions(close: pd.Series, har_ann_vol: pd.Series) -> dict[str, pd.Series]:
    sig = baselines.trend_signal(close)
    return {
        "buy_and_hold": baselines.buy_and_hold(close.index),
        "trend": sig,
        "trend_ewma": baselines.vol_scaled(sig, baselines.ewma_vol(close), TARGET_VOL),
        "trend_har": baselines.vol_scaled(sig, har_ann_vol, TARGET_VOL),
    }


def run(symbols=("BTCUSDT", "ETHUSDT"), cost: CostModel | None = None) -> dict:
    cost = cost or CostModel()
    stressed = cost.stressed(2.0)
    returns, rows, yearly, volrows = {}, [], [], []
    for sym in symbols:
        daily, hourly = load_bars(sym, "1d"), load_bars(sym, "1h")
        close = daily["close"]
        rv = har.daily_rv_from_hourly(hourly)
        har_var = har.har_forecast(rv)
        har_vol = np.sqrt(har_var * 365).reindex(close.index)
        start = har_vol.first_valid_index()
        pos = _positions(close, har_vol)

        # volatility forecast quality on the days where every forecast exists
        ewma_var = har.ewma_variance_forecast(close).reindex(rv.index)
        nxt = rv.shift(-1)
        common = har_var.dropna().index.intersection(ewma_var.dropna().index).intersection(nxt.dropna().index)
        for name, f in (("HAR-RV", har_var), ("EWMA 0.94", ewma_var), ("yesterday's RV", rv)):
            volrows.append({"symbol": sym, "forecaster": name, "qlike": har.qlike(f.loc[common], nxt.loc[common]), "days": len(common)})

        for strat in STRATEGIES:
            res = backtest.run(close.loc[start:], pos[strat].loc[start:], cost, BAND)
            res2 = backtest.run(close.loc[start:], pos[strat].loc[start:], stressed, BAND)
            years = len(res) / 365
            row = {
                "symbol": sym, "strategy": strat, "start": str(start.date()), "days": len(res),
                **{f"net_{k}": v for k, v in metrics.summarize(res["net"]).items()},
                "sharpe_gross": metrics.sharpe(res["gross"]),
                "sharpe_net_2x_costs": metrics.sharpe(res2["net"]),
                "cost_drag_per_year": float(res["cost"].sum() / years),
                "turnover_per_year": float(res["turnover"].sum() / years),
                "avg_exposure": float(res["position"].mean()),
                "sharpe_period": float(res["net"].mean() / res["net"].std(ddof=1)),
            }
            rows.append(row)
            returns[f"{sym}:{strat}"] = res["net"]
            for year, grp in res["net"].groupby(res.index.year):
                yearly.append({"symbol": sym, "strategy": strat, "year": int(year), "return": float((1 + grp).prod() - 1),
                               "sharpe": metrics.sharpe(grp), "days": len(grp)})
    trial_sharpes = [r["sharpe_period"] for r in rows]
    for r in rows:
        r["deflated_sharpe"] = metrics.deflated_sharpe(returns[f"{r['symbol']}:{r['strategy']}"], trial_sharpes)
        r["n_trials"] = len(trial_sharpes)
        emit("eval.trial", service="eval", family="baselines-v1", name=f"{r['symbol']}:{r['strategy']}",
             sharpe_period=r["sharpe_period"], n=r["days"], deflated_sharpe=r["deflated_sharpe"])
    ret = pd.DataFrame(returns)
    return {"rows": rows, "yearly": yearly, "vol": volrows, "returns": ret, "cost": cost}


def _pct(x: float, nd: int = 1) -> str:
    return "n/a" if x != x else f"{x * 100:.{nd}f}%"


def to_markdown(res: dict) -> str:
    c = res["cost"]
    lines = [
        "# Phase 1 baselines on real data",
        "",
        f"Costs: {c.fee_bps:g} bps fee + {c.slippage_bps:g} bps slippage per side ({c.round_trip() * 1e4:g} bps round trip), both ASSUMED, "
        f"plus a 2x stress. Spot, long-only, no leverage, daily bars, no-trade band {BAND:.0%}, volatility target {TARGET_VOL:.0%}.",
        "",
        "## Strategy results (net of costs, common sample per asset)",
        "",
        "| Asset | Strategy | Days | CAGR | Vol | Sharpe | Sharpe at 2x costs | Max DD | Worst day | Exposure | Turnover/yr | Cost drag/yr | Deflated Sharpe |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in res["rows"]:
        lines.append(
            f"| {r['symbol']} | {r['strategy']} | {r['days']} | {_pct(r['net_cagr'])} | {_pct(r['net_vol'])} | {r['net_sharpe']:.2f} | "
            f"{r['sharpe_net_2x_costs']:.2f} | {_pct(r['net_max_drawdown'])} | {_pct(r['net_worst_day'])} | {_pct(r['avg_exposure'], 0)} | "
            f"{r['turnover_per_year']:.1f} | {_pct(r['cost_drag_per_year'], 2)} | {r['deflated_sharpe']:.2f} |"
        )
    lines += ["", f"Deflated Sharpe counts {res['rows'][0]['n_trials']} trials (every asset and strategy above). It is the probability the true Sharpe is above zero after that many tries.", "",
              "## Volatility forecast quality (QLIKE loss, lower is better)", "", "| Asset | Forecaster | QLIKE | Days |", "|---|---|---:|---:|"]
    for v in res["vol"]:
        lines.append(f"| {v['symbol']} | {v['forecaster']} | {v['qlike']:.4f} | {v['days']} |")
    lines += ["", "## Net return by calendar year", "", "| Asset | Strategy | " + " | ".join(str(y) for y in sorted({y['year'] for y in res['yearly']})) + " |",
              "|---|---|" + "---:|" * len({y['year'] for y in res['yearly']})]
    years = sorted({y["year"] for y in res["yearly"]})
    for sym in sorted({y["symbol"] for y in res["yearly"]}):
        for strat in STRATEGIES:
            cells = {y["year"]: y for y in res["yearly"] if y["symbol"] == sym and y["strategy"] == strat}
            lines.append(f"| {sym} | {strat} | " + " | ".join(_pct(cells[y]["return"], 0) if y in cells else "" for y in years) + " |")
    return "\n".join(lines) + "\n"
