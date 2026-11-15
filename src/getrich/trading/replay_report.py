"""Run the replay on stored history at normal and doubled costs, compare with the research baselines, and write a report."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..eval import backtest, baselines, metrics
from ..eval.baseline_report import BAND, TARGET_VOL
from ..eval.costs import CostModel
from ..eval.data import load_bars
from . import limits as L
from .replay import SYMBOLS, ReplayConfig, ReplayResult, run


def _baseline_returns(bars: dict, idx: pd.Index, costs: CostModel) -> dict[str, pd.Series]:
    out = {}
    for name, fn in (("buy and hold", lambda c: baselines.buy_and_hold(c.index)),
                     ("vol-scaled trend (research baseline)", lambda c: baselines.vol_scaled(baselines.trend_signal(c), baselines.ewma_vol(c), TARGET_VOL))):
        per = [backtest.run(bars[s]["close"], fn(bars[s]["close"]), costs, BAND if "vol" in name else 0.0)["net"] for s in SYMBOLS]
        out[name] = pd.concat(per, axis=1).mean(axis=1).reindex(idx).fillna(0.0)      # equal weight across BTC and ETH
    return out


def _stats(r: pd.Series) -> dict:
    s = metrics.summarize(r)
    s["total"] = float((1 + r).prod() - 1)
    return s


def run_all(limits: L.Limits | None = None) -> dict:
    if limits is None:
        limits, why = L.load()
        if limits is None:
            raise RuntimeError(f"cannot replay without usable limits: {why}")
    bars = {s: load_bars(s, "1d") for s in SYMBOLS}
    res = {}
    for label, mult in (("base costs", 1.0), ("2x costs", 2.0)):
        costs = CostModel().stressed(mult) if mult != 1.0 else CostModel()
        r = run(bars, ReplayConfig(limits=limits, costs=costs))
        res[label] = {"result": r, "baselines": _baseline_returns(bars, r.equity.index, costs)}
    return {"runs": res, "limits": limits, "start": res["base costs"]["result"].equity.index[0], "end": res["base costs"]["result"].equity.index[-1]}


def _drawdown_info(equity: pd.Series) -> str:
    peak = equity.cummax()
    dd = equity / peak - 1
    trough = dd.idxmin()
    peak_day = equity.loc[:trough].idxmax()
    return (f"worst drawdown {dd.min():.1%} from the peak on {peak_day:%Y-%m-%d} (${equity.loc[peak_day]:.0f}) to the trough on {trough:%Y-%m-%d} (${equity.loc[trough]:.0f}); "
            f"at the end of the data equity is ${equity.iloc[-1]:.0f}, {dd.iloc[-1]:.1%} below its peak")


def _first_trade_day(r: ReplayResult) -> pd.Timestamp:
    return r.trades["entry"].min() if len(r.trades) else r.equity.index[0]


def to_markdown(out: dict) -> str:
    lim, base = out["limits"], out["runs"]["base costs"]
    r: ReplayResult = base["result"]
    t = r.trades
    first = _first_trade_day(r)
    window = r.returns[r.returns.index >= first]
    L_ = [f"# Replay of the order path on stored history", "",
          f"{out['start']:%Y-%m-%d} to {out['end']:%Y-%m-%d} ({len(r.equity)} days; trading starts {first:%Y-%m-%d} when the slowest trend pair has data). "
          f"BTCUSDT and ETHUSDT daily bars, start equity ${r.config.start_equity:.0f}. Every entry went through the real risk gate with the approved "
          f"`{lim.profile}` limits (exposure cap {lim.max_exposure_fraction:.0%}, drawdown halt {lim.account_drawdown_halt:.0%}, daily loss halt {lim.daily_loss_halt:.1%}) "
          f"and the project cost model (10 bps fee and 5 bps slippage per side; 2x shown too).", "",
          "Rule, fixed before running (the Phase 3 pre-registered primary rule, nothing tuned here): enter at 2/3 or more trend votes when flat; "
          "stop 2 sigma below, take profit 4 sigma above, sell at the close after 20 days; one position per symbol.", "",
          "## Did the system behave?", ""]
    for label, d in out["runs"].items():
        rr: ReplayResult = d["result"]
        L_.append(f"- **{label}:** {len(rr.violations)} invariant violations over {len(rr.trades)} trades "
                  f"(at entry: risk per trade at most {lim.risk_per_trade:.1%} of equity, exposure at most {lim.max_exposure_fraction:.0%}, whole exchange steps, minimum size, cash never negative, nothing opened under a halt)."
                  + (f" First: {rr.violations[0]}" if rr.violations else "") + (f" Drawdown halt tripped on {rr.halted_on:%Y-%m-%d}." if rr.halted_on is not None else " The drawdown halt never tripped."))
    L_.append(f"- The exposure cap binds when a position is opened and positions are not trimmed afterwards, so a winner drifts above it: the marked exposure peaked at {r.exposure.max():.1%} of equity. "
              f"The worst single trade lost {(t.r.min() if len(t) else 0):.2f} R (a gap through a stop loses more than the risk budget).")
    L_.append(f"- Base-cost equity: {_drawdown_info(r.equity)}.")
    rej = ", ".join(f"{k} {v}" for k, v in r.rejections.most_common()) or "none"
    L_ += [f"- Signal days with a flat symbol: {sum(r.signal_days.values())}; entries taken {len(t)}; gate refusals by first failing check: {rej}.", "",
           "## Results", "",
           "| | Total return | CAGR | Sharpe | Max drawdown | Worst day | vs. buy and hold Sharpe |", "|---|---:|---:|---:|---:|---:|---:|"]
    bh_sharpe = {}
    for label, d in out["runs"].items():
        rr = d["result"]
        w = rr.returns[rr.returns.index >= first]
        bw = {k: v[v.index >= first] for k, v in d["baselines"].items()}
        bh_sharpe[label] = _stats(bw["buy and hold"])["sharpe"]
        for name, ret in ((f"gated trend rule, {label}", w), *[(f"{k}, {label}", v) for k, v in bw.items()]):
            s = _stats(ret)
            L_.append(f"| {name} | {s['total']:+.1%} | {s['cagr']:+.1%} | {s['sharpe']:.2f} | {s['max_drawdown']:.1%} | {s['worst_day']:+.1%} | "
                      + (f"{s['sharpe'] - bh_sharpe[label]:+.2f} |" if name.startswith("gated") else "|"))
    L_ += ["", "Sharpe does not depend on how much is invested, so it compares the gated rule with the full-size baselines fairly. "
           "Total return and drawdown do not: the approved limits cap the gated rule's risk per trade and total exposure, so its return is small by design.", ""]
    if len(t):
        gross_win, gross_loss = t.loc[t.pnl > 0, "pnl"].sum(), -t.loc[t.pnl <= 0, "pnl"].sum()
        L_ += ["## Trades (base costs)", "",
               f"- {len(t)} trades, {(t.pnl > 0).mean():.0%} winners, average {t.r.mean():+.2f} R, median {t.r.median():+.2f} R, profit factor {gross_win / gross_loss if gross_loss else float('inf'):.2f}.",
               f"- Exits: " + ", ".join(f"{k} {v}" for k, v in t.kind.value_counts().items()) + f". Average hold {t.days.mean():.1f} days. Fees paid ${t.fees.sum():.2f} against net profit ${t.pnl.sum():+.2f}.",
               f"- Average exposure {r.exposure[r.exposure.index >= first].mean():.1%} of equity; in the market {(r.exposure[r.exposure.index >= first] > 0).mean():.0%} of days.", "",
               "| Year | Trades | Net P&L | Avg R | Gated return | Buy and hold return |", "|---|---:|---:|---:|---:|---:|"]
        yr = r.returns.groupby(r.returns.index.year).apply(lambda x: (1 + x).prod() - 1)
        bh = base["baselines"]["buy and hold"].groupby(base["baselines"]["buy and hold"].index.year).apply(lambda x: (1 + x).prod() - 1)
        for y, g in t.groupby(t.entry.dt.year):
            L_.append(f"| {y} | {len(g)} | {g.pnl.sum():+.2f} | {g.r.mean():+.2f} | {yr.get(y, 0):+.1%} | {bh.get(y, 0):+.1%} |")
        L_ += ["", "| Symbol | Trades | Net P&L | Avg R |", "|---|---:|---:|---:|"]
        for s, g in t.groupby("symbol"):
            L_.append(f"| {s} | {len(g)} | {g.pnl.sum():+.2f} | {g.r.mean():+.2f} |")
    L_ += ["", "## How to read this", "",
           "- This is one rule on one history that the research already looked at, so it cannot confirm an edge. Phase 1 and Phase 3 put the same rule's Deflated Sharpe below the 0.90 bar.",
           "- A pass here means the plumbing behaves on real data (limits respected, costs paid, halts honoured). It does not mean the rule is profitable going forward.",
           "- Results at 2x costs show how fragile the rule is to costs, which are assumptions until measured with micro-live trading."]
    return "\n".join(L_) + "\n"
