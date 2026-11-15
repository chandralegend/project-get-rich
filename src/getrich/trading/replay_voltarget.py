"""Replay the volatility-scaled trend strategy through the REAL order path (same gate, costs and approved limits).

The research baseline sizes each coin as trend_signal x min(1, 20% / EWMA volatility) and rebalances freely. The gate does not allow
that: it permits one position per symbol and no adding, so the gate-compatible version is the one defined here, fixed in advance:

  * target weight of equity per coin = 0.5 x trend_signal x min(1, 0.20 / EWMA vol)   (two equal sleeves, as in the research baseline)
  * flat and target above zero: BUY through the gate, requested size = the target, which the gate may only reduce
    (risk budget, exposure cap, cash, exchange minimums); a protective stop 3 sigma below the fill, set once and never moved, no take profit
  * holding and the target has fallen below the current weight by 10 points of equity or more: SELL the difference (always allowed)
  * holding and the target is zero: SELL everything
  * adds are not possible: when the signal strengthens or volatility falls, the position stays as it is

Nothing is tuned: the 3 sigma stop was fixed before the first run and is the only value tried.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from ..eval import baselines
from ..eval.baseline_report import BAND, TARGET_VOL
from ..eval.labels import EPS, daily_vol
from . import limits as L
from .gate import evaluate
from .replay import ReplayConfig, ReplayResult
from .types import DEFAULT_RULES, OrderIntent, PortfolioState, Position

STOP_SIGMA = 3.0
SLEEVE = 0.5


def run(bars: dict[str, pd.DataFrame], cfg: ReplayConfig, entry_min_signal: float = 0.0) -> tuple[ReplayResult, dict]:
    syms = [s for s in cfg.symbols if s in bars]
    idx = bars[syms[0]].index
    for s in syms[1:]:
        idx = idx.intersection(bars[s].index)
    px = {s: bars[s].reindex(idx) for s in syms}
    sig = {s: baselines.trend_signal(px[s]["close"]) for s in syms}
    ewma = {s: baselines.ewma_vol(px[s]["close"]) for s in syms}
    target = {s: (SLEEVE * baselines.vol_scaled(sig[s], ewma[s], TARGET_VOL)).fillna(0.0) for s in syms}
    sigma = {s: daily_vol(px[s]["close"]) for s in syms}
    slip, fee = cfg.costs.slippage_bps / 1e4, cfg.costs.fee_bps / 1e4

    cash, equity_prev, peak, halted_on = cfg.start_equity, cfg.start_equity, cfg.start_equity, None
    pos: dict[str, dict] = {}
    violations, rejections, binding = [], Counter(), Counter()
    events = Counter()
    eq, expo, wanted = [], [], []

    def sell(s: str, qty: float, price: float) -> float:
        fill = price * (1 - slip)
        proceeds = qty * fill
        return proceeds - proceeds * fee

    for i, day in enumerate(idx):
        for s in list(pos):                                       # protective stops, tested against this bar
            p = pos[s]
            o, l = float(px[s]["open"].iloc[i]), float(px[s]["low"].iloc[i])
            if l <= p["stop"] * (1 + EPS):
                cash += sell(s, p["qty"], min(p["stop"], o))
                events["stop"] += 1
                del pos[s]

        marks = {s: float(px[s]["close"].iloc[i]) for s in syms}
        equity = cash + sum(p["qty"] * marks[s] for s, p in pos.items())
        peak = max(peak, equity)
        latched = halted_on is not None
        if not latched and (peak - equity) / peak >= cfg.limits.account_drawdown_halt:
            halted_on, latched = day, True

        for s in syms:
            sg, tw, c = sigma[s].iloc[i], float(target[s].iloc[i]), marks[s]
            if not np.isfinite(sg) or sg <= 0:
                continue
            cur_w = pos[s]["qty"] * c / equity if s in pos else 0.0
            state = PortfolioState(
                now=day, equity=equity, cash=cash, peak_equity=peak, day_start_equity=equity_prev,
                positions={k: Position(k, q["qty"], q["fill"], q["stop"], None, "r", q["day"]) for k, q in pos.items()},
                prices={k: (marks[k], 0.0, "1d") for k in syms}, halt_latched=latched, limits_ok=True)
            if s in pos:
                if tw <= 0.0 or (cur_w - tw) >= BAND:
                    qty = pos[s]["qty"] if tw <= 0.0 else (cur_w - tw) * equity / c
                    v = evaluate(OrderIntent(s, "sell", qty=qty, source="voltarget_replay"), state, cfg.limits, costs=cfg.costs)
                    if v.approved and v.qty > 0:
                        cash += sell(s, v.qty, c)
                        pos[s]["qty"] -= v.qty
                        events["exit" if pos[s]["qty"] <= 1e-12 else "trim"] += 1
                        if pos[s]["qty"] <= 1e-12:
                            del pos[s]
                continue
            if tw <= 0.0 or float(sig[s].iloc[i]) < entry_min_signal - 1e-9:
                continue
            wanted.append(tw)
            intent = OrderIntent(s, "buy", qty=tw * equity / c, stop_price=c * (1 - STOP_SIGMA * sg), source="voltarget_replay")
            v = evaluate(intent, state, cfg.limits, costs=cfg.costs)
            if not v.approved:
                rejections[next((n for n, ok, _ in v.checks if not ok), "unknown")] += 1
                continue
            sizing = next((d for n, ok, d in v.checks if n == "sizing"), "")
            binding[sizing.split(":")[0].replace("limited by ", "")] += 1
            fill = c * (1 + slip)
            cost = v.qty * fill
            entry_fee = cost * fee
            step = DEFAULT_RULES[s].step
            if v.risk_amount > equity * cfg.limits.risk_per_trade + 1e-9:
                violations.append(f"{day:%Y-%m-%d} {s}: risk {v.risk_amount:.4f} above {cfg.limits.risk_per_trade:.2%} of equity")
            if state.exposure + v.qty * c > cfg.limits.max_exposure_fraction * equity + 1e-6:
                violations.append(f"{day:%Y-%m-%d} {s}: exposure above the {cfg.limits.max_exposure_fraction:.0%} cap")
            if abs(v.qty / step - round(v.qty / step)) > 1e-6:
                violations.append(f"{day:%Y-%m-%d} {s}: quantity breaks the exchange step")
            if cash - cost - entry_fee < -1e-9:
                violations.append(f"{day:%Y-%m-%d} {s}: cash would go negative")
            if latched:
                violations.append(f"{day:%Y-%m-%d} {s}: entered while the drawdown halt was latched")
            cash -= cost + entry_fee
            pos[s] = {"qty": v.qty, "fill": fill, "stop": intent.stop_price, "day": day}
            events["entry"] += 1
            if v.reasons:                                         # cut below the request by a limit, not just rounded down to the exchange step
                events["entry_cut_by_a_limit"] += 1

        equity = cash + sum(p["qty"] * marks[s] for s, p in pos.items())
        eq.append(equity)
        expo.append(sum(p["qty"] * marks[s] for s, p in pos.items()) / equity if equity > 0 else 0.0)
        equity_prev = equity

    res = ReplayResult(pd.Series(eq, index=idx), pd.DataFrame(), rejections, violations, halted_on, {}, pd.Series(expo, index=idx), cfg)
    return res, {"events": dict(events), "binding": dict(binding), "mean_requested_weight": float(np.mean(wanted)) if wanted else 0.0}


def run_all(limits: L.Limits | None = None) -> dict:
    from ..eval import metrics
    from ..eval.costs import CostModel
    from ..eval.data import load_bars
    from . import replay_report as rr
    from .replay import SYMBOLS, run as run_trend

    if limits is None:
        limits, why = L.load()
        if limits is None:
            raise RuntimeError(f"cannot replay without usable limits: {why}")
    bars = {s: load_bars(s, "1d") for s in SYMBOLS}
    out = {}
    for label, mult in (("base costs", 1.0), ("2x costs", 2.0)):
        costs = CostModel().stressed(mult) if mult != 1.0 else CostModel()
        cfg = ReplayConfig(limits=limits, costs=costs)
        res, info = run(bars, cfg)
        trend = run_trend(bars, cfg)
        out[label] = {"vt": res, "info": info, "trend": trend, "baselines": rr._baseline_returns(bars, res.equity.index, costs)}
    return {"runs": out, "limits": limits, "start": res.equity.index[0], "end": res.equity.index[-1]}


def to_markdown(out: dict) -> str:
    from ..eval import metrics

    lim = out["limits"]
    first = out["runs"]["base costs"]["trend"].trades["entry"].min()      # same window as the main replay report: from the first day the slowest trend pair has data

    def row(name, r):
        r = r[r.index >= first]
        return (f"| {name} | {(1 + r).prod() - 1:+.1%} | {metrics.cagr(r):+.1%} | {metrics.sharpe(r):.2f} | {metrics.max_drawdown(r):.1%} | {r.min():+.1%} |")
    base, hard = out["runs"]["base costs"], out["runs"]["2x costs"]
    info, vt = base["info"], base["vt"]
    L_ = ["# Volatility-scaled trend through the gate", "",
          f"{first:%Y-%m-%d} to {out['end']:%Y-%m-%d}, BTCUSDT and ETHUSDT daily bars, start equity $500, limits: {lim.profile} (exposure {lim.max_exposure_fraction:.0%}, "
          f"drawdown halt {lim.account_drawdown_halt:.0%}, daily halt {lim.daily_loss_halt:.1%}, risk per trade {lim.risk_per_trade:.1%}). Every buy and sell went through the real gate.", "",
          "Rule (fixed in advance, see `trading/replay_voltarget.py`): target weight = 0.5 x trend signal x min(1, 20% / EWMA vol) per coin; buy through the gate when flat, sell down when the target "
          "falls 10 points below the current weight, exit at zero; a protective stop 3 sigma below the fill, set once. The gate allows one position per symbol and no adding, so a position keeps the size it was bought at.", "",
          "## Did the system behave?", "",
          f"- Invariant violations: base {len(vt.violations)}, 2x {len(hard['vt'].violations)}. Drawdown halt: base {vt.halted_on.date() if vt.halted_on is not None else 'never tripped'}, "
          f"2x {hard['vt'].halted_on.date() if hard['vt'].halted_on is not None else 'never tripped'}.",
          f"- Events (base): {info['events']}. Gate refusals by first failing check: {dict(vt.rejections) or 'none'}. What bounded each entry's size: {info['binding']}.",
          f"- Average requested position {info['mean_requested_weight']:.1%} of equity; average marked exposure {vt.exposure.mean():.1%}. The limits did not bind: the volatility target already keeps positions far below the cap.", "",
          "## Results", "", "| | Total return | CAGR | Sharpe | Max drawdown | Worst day |", "|---|---:|---:|---:|---:|---:|",
          row("vol-scaled trend through the gate, base costs", vt.returns), row("vol-scaled trend through the gate, 2x costs", hard["vt"].returns),
          row("gated trend rule (stop 2 sigma, take profit 4 sigma), base costs", base["trend"].returns), row("gated trend rule, 2x costs", hard["trend"].returns),
          row("vol-scaled trend, research baseline (free rebalancing, no gate), base costs", base["baselines"]["vol-scaled trend (research baseline)"]),
          row("buy and hold, equal weight BTC and ETH", base["baselines"]["buy and hold"]), "",
          "## Reading it", "",
          "- The gate-compatible version earns less than the research baseline because it cannot add: a position opened at one or two trend votes stays small even when the trend strengthens, and the 3 sigma stops (15 of them) probably end positions the baseline would have kept.",
          "- Its risk is small and steady. Compared with the gated trend rule under the same limits it has a lower drawdown for a comparable or better Sharpe, which is the point of volatility scaling.",
          "- Everything here is in-sample on one crypto cycle, with one pre-declared stop multiple. It is not a test of an edge, and buy and hold still returned far more.", ""]
    return "\n".join(L_)


PREREG = "docs/preregistration-voltarget-entry.md"


def study(limits: L.Limits | None = None, register: bool = True, require_prereg: bool = True, bars: dict | None = None) -> dict:
    """The pre-registered comparison of entering at 1 of 3 votes (V1) against 2 of 3 votes (V2). See docs/preregistration-voltarget-entry.md."""
    from ..eval import metrics, trials
    from ..eval.channel_ablation import prereg_events, prereg_hash
    from ..eval.costs import CostModel
    from ..eval.data import load_bars
    from .replay import SYMBOLS, run as run_trend

    h = prereg_hash(PREREG) if require_prereg else None
    if require_prereg and h not in {e.get("sha256") for e in prereg_events()}:
        raise RuntimeError("the voltarget pre-registration does not match any logged hash: run `getrich preregister docs/preregistration-voltarget-entry.md`")
    if limits is None:
        limits, why = L.load()
        if limits is None:
            raise RuntimeError(f"cannot replay without usable limits: {why}")
    bars = bars or {s: load_bars(s, "1d") for s in SYMBOLS}
    runs = {}
    for label, mult in (("base", 1.0), ("2x", 2.0)):
        cfg = ReplayConfig(limits=limits, costs=CostModel().stressed(mult) if mult != 1.0 else CostModel())
        v1, i1 = run(bars, cfg, 0.0)
        v2, i2 = run(bars, cfg, 2 / 3)
        runs[label] = {"V1": (v1, i1), "V2": (v2, i2), "trend": run_trend(bars, cfg)}
    first = runs["base"]["trend"].trades["entry"].min()

    def window(r):
        return r[r.index >= first]
    rows = {}
    base_period = {k: float(window(runs["base"][k][0].returns).mean() / window(runs["base"][k][0].returns).std(ddof=1)) for k in ("V1", "V2")}
    all_trials = trials.period_sharpes() + list(base_period.values())
    for k in ("V1", "V2"):
        rb, rh = window(runs["base"][k][0].returns), window(runs["2x"][k][0].returns)
        mid = rh.index[len(rh) // 2]
        rows[k] = {"sharpe": metrics.sharpe(rb), "sharpe_2x": metrics.sharpe(rh), "cagr": metrics.cagr(rb), "total": float((1 + rb).prod() - 1), "max_dd": metrics.max_drawdown(rb),
                   "half1_2x": metrics.sharpe(rh[rh.index < mid]), "half2_2x": metrics.sharpe(rh[rh.index >= mid]), "dsr": metrics.deflated_sharpe(rb, all_trials),
                   "entries": runs["base"][k][1]["events"].get("entry", 0), "stops": runs["base"][k][1]["events"].get("stop", 0),
                   "violations": len(runs["base"][k][0].violations) + len(runs["2x"][k][0].violations),
                   "halted": runs["base"][k][0].halted_on is not None or runs["2x"][k][0].halted_on is not None,
                   "exposure": float(window(runs["base"][k][0].exposure).mean())}
    trend_2x = metrics.sharpe(window(runs["2x"]["trend"].returns))
    trend_base = window(runs["base"]["trend"].returns)
    rows["trend"] = {"sharpe": metrics.sharpe(trend_base), "sharpe_2x": trend_2x, "cagr": metrics.cagr(trend_base), "total": float((1 + trend_base).prod() - 1), "max_dd": metrics.max_drawdown(trend_base)}
    v2 = rows["V2"]
    crit = {"gain_vs_V1_and_trend": v2["sharpe_2x"] - rows["V1"]["sharpe_2x"] >= 0.10 and v2["sharpe_2x"] - trend_2x >= 0.10, "dsr": v2["dsr"] >= 0.90,
            "drawdown": v2["max_dd"] <= 0.20, "both_halves_positive": v2["half1_2x"] > 0 and v2["half2_2x"] > 0, "clean": v2["violations"] == 0 and not v2["halted"]}
    v2["criteria"], v2["shows_value"] = crit, all(crit.values())
    if register:
        trials.register(4, "voltarget-gate-v1:entry-1of3", rows["V1"]["sharpe"], "docs/phase4-voltarget-entry.md")
        trials.register(4, "voltarget-gate-v1:entry-2of3", rows["V2"]["sharpe"], "docs/phase4-voltarget-entry.md")
    from ..obs.events import emit

    emit("eval.voltarget_entry_run", service="eval", prereg_sha256=h, n_trials=len(all_trials), shows_value=v2["shows_value"])
    return {"rows": rows, "limits": limits, "prereg": h, "n_trials": len(all_trials), "start": first, "end": runs["base"]["V1"][0].equity.index[-1]}


def study_markdown(res: dict) -> str:
    R, lim = res["rows"], res["limits"]
    def pct(x):
        return f"{x * 100:.1f}%"
    L_ = ["# Gated volatility-scaled trend: entry at 1 of 3 votes versus 2 of 3 (pre-registered)", "",
          f"Pre-registration: `{PREREG}`, SHA-256 `{(res['prereg'] or 'unchecked')[:16]}...` (matches the hash logged before the run). "
          f"{res['start']:%Y-%m-%d} to {res['end']:%Y-%m-%d}; limits {lim.profile} (exposure {lim.max_exposure_fraction:.0%}, halt {lim.account_drawdown_halt:.0%}, risk per trade {lim.risk_per_trade:.1%}). "
          f"Deflated Sharpe counts {res['n_trials']} trials.", "",
          "| | Total | CAGR | Sharpe | at 2x costs | Max DD | Half 1 / half 2 at 2x | Deflated Sharpe | Entries / stops | Avg exposure |", "|---|---:|---:|---:|---:|---:|---|---:|---|---:|"]
    for k, name in (("V1", "V1, enter at 1 of 3 votes"), ("V2", "V2, enter at 2 of 3 votes")):
        r = R[k]
        L_.append(f"| {name} | {r['total']:+.1%} | {pct(r['cagr'])} | {r['sharpe']:.2f} | {r['sharpe_2x']:.2f} | {pct(r['max_dd'])} | {r['half1_2x']:.2f} / {r['half2_2x']:.2f} | {r['dsr']:.3f} | {r['entries']} / {r['stops']} | {pct(r['exposure'])} |")
    t = R["trend"]
    L_.append(f"| reference: gated 2 sigma / 4 sigma trend rule | {t['total']:+.1%} | {pct(t['cagr'])} | {t['sharpe']:.2f} | {t['sharpe_2x']:.2f} | {pct(t['max_dd'])} | | | | |")
    c = R["V2"]["criteria"]
    verdict = "**V2 shows value**" if R["V2"]["shows_value"] else "**V2: not shown** (" + ", ".join(k for k, ok in c.items() if not ok) + " failed)"
    L_ += ["", verdict, "", "Criteria (all required for V2): Sharpe at 2x costs at least 0.10 above both V1 and the gated trend rule, Deflated Sharpe at least 0.90, maximum drawdown at most 20%, "
           "positive Sharpe at 2x costs in both halves, zero invariant violations and no halt.", ""]
    return "\n".join(L_)
