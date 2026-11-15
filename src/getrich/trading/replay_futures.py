"""Replay hourly bars through the REAL risk gate with a margin account: long and short, leverage, funding, liquidation.

This is the research engine for day-trading style rules. It uses the same gate, cost model and limits type as paper trading,
with limits that allow shorting and leverage (`allow_short`, `max_leverage`). It is a replay only: the paper and testnet path
is spot and refuses shorts (see service.propose).

Account model (USDT-margined perpetual, cross margin, one-way mode), written down so nothing is hidden:
  * wallet = starting cash + realised profit - fees - funding. Opening a position costs only its fee; the margin is not spent, it is reserved.
  * equity = wallet + unrealised profit at the last close. Gross exposure = sum of position notionals.
  * entries and exits fill at the close (or the stop / take-profit level, or the open if the bar gapped through it) with the cost model's
    fee and slippage on each side; a bar that touches both stop and take profit counts as the stop.
  * funding is paid or received every 8 hours (00:00, 08:00, 16:00 UTC) on the notional at that bar's open. The rate is an ASSUMPTION
    (default 0.01% per 8 hours, longs pay and shorts receive); real history has not been downloaded.
  * liquidation: if, at the worst price of a bar for every open position at once, equity falls to MAINTENANCE_MARGIN of the gross notional, the
    account is liquidated and the wallet is lost. The gate's stop-versus-liquidation buffer is meant to make that impossible; if it ever
    happens it is reported as a violation.
  * mark price equals the traded price and the perpetual's basis to spot is ignored.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from ..eval.costs import CostModel
from ..eval.labels import EPS
from . import limits as L
from .gate import evaluate
from .types import DEFAULT_RULES, OrderIntent, PortfolioState, Position

SYMBOLS = ("BTCUSDT", "ETHUSDT")
FUNDING_HOURS = (0, 8, 16)
FUNDING_8H = 0.0001            # ASSUMED 0.01% per 8 hours (Binance's default interest component); replace with history once approved
STOP_FLOOR = 0.015             # the cost gate refuses stops under about 1.2% at 30 bps round trip, so rules must not ask for tighter


@dataclass(frozen=True)
class FuturesConfig:
    limits: L.Limits
    start_equity: float = 500.0
    horizon_bars: int = 48
    rr: float = 2.0                                  # take profit at rr times the stop distance
    costs: CostModel = field(default_factory=CostModel)
    funding_8h: float = FUNDING_8H
    symbols: tuple[str, ...] = SYMBOLS


@dataclass
class FuturesResult:
    equity: pd.Series
    trades: pd.DataFrame
    rejections: Counter
    violations: list[str]
    halted_on: pd.Timestamp | None
    liquidated_on: pd.Timestamp | None
    funding_paid: float
    signal_bars: dict[str, int]
    exposure: pd.Series
    config: FuturesConfig

    @property
    def returns(self) -> pd.Series:
        return self.equity.pct_change().replace([np.inf, -np.inf], 0.0).fillna(0.0)

    def daily_returns(self) -> pd.Series:
        eq = self.equity.groupby(self.equity.index.floor("D")).last()
        return eq.pct_change().replace([np.inf, -np.inf], 0.0).fillna(0.0)


# ---------------------------------------------------------------------------------------------------------------- the rule

def breakout_signals(px: pd.DataFrame, lookback: int = 24, fast: int = 12, slow: int = 48, atr_n: int = 24, atr_mult: float = 3.0) -> tuple[pd.Series, pd.Series]:
    """(direction, stop distance as a fraction of price), decided at each bar's close from data up to and including that bar.
    Long when the close breaks above the previous `lookback` bars' highest high and the fast EMA is above the slow EMA; short is the mirror.
    The stop is atr_mult times the average true range, never tighter than STOP_FLOOR."""
    c, h, l = px["close"], px["high"], px["low"]
    ema_f, ema_s = c.ewm(span=fast, adjust=False).mean(), c.ewm(span=slow, adjust=False).mean()
    prev_hi, prev_lo = h.shift(1).rolling(lookback).max(), l.shift(1).rolling(lookback).min()
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(atr_n).mean()
    long_ = (c > prev_hi) & (ema_f > ema_s)
    short_ = (c < prev_lo) & (ema_f < ema_s)
    direction = pd.Series(0, index=px.index).mask(long_, 1).mask(short_, -1)
    direction[atr.isna() | prev_hi.isna()] = 0
    stop = (atr_mult * atr / c).clip(lower=STOP_FLOOR)
    return direction, stop


# ---------------------------------------------------------------------------------------------------------------- the engine

def run(bars: dict[str, pd.DataFrame], cfg: FuturesConfig, strategy: Callable = breakout_signals, allow_longs: bool = True, allow_shorts: bool = True) -> FuturesResult:
    syms = [s for s in cfg.symbols if s in bars]
    idx = bars[syms[0]].index
    for s in syms[1:]:
        idx = idx.intersection(bars[s].index)
    px = {s: bars[s].reindex(idx) for s in syms}
    sig = {s: strategy(px[s]) for s in syms}
    slip, fee = cfg.costs.slippage_bps / 1e4, cfg.costs.fee_bps / 1e4
    lim = cfg.limits

    wallet, equity_prev, peak, halted_on, liquidated_on = cfg.start_equity, cfg.start_equity, cfg.start_equity, None, None
    day_start_eq, cur_day, funding_paid = cfg.start_equity, None, 0.0
    pos: dict[str, dict] = {}
    trades, violations, rejections, signal_bars = [], [], Counter(), Counter()
    eq, expo = [], []
    ohlc = {s: {k: px[s][k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")} for s in syms}

    def close_out(s: str, p: dict, kind: str, ref: float, ts: pd.Timestamp, i: int) -> None:
        nonlocal wallet
        fill = ref * (1 - slip) if p["sign"] > 0 else ref * (1 + slip)
        exit_fee = p["qty"] * fill * fee
        gross = p["sign"] * (fill - p["fill"]) * p["qty"]
        wallet += gross - exit_fee
        pnl = gross - exit_fee - p["fee"]
        trades.append({"symbol": s, "side": "long" if p["sign"] > 0 else "short", "entry": p["day"], "exit": ts, "bars": i - p["i"], "qty": p["qty"], "entry_px": p["fill"],
                       "exit_px": fill, "kind": kind, "pnl": pnl, "risk": p["risk"], "r": pnl / p["risk"] if p["risk"] > 0 else np.nan, "fees": p["fee"] + exit_fee,
                       "notional": p["qty"] * p["fill"]})
        del pos[s]

    for i, ts in enumerate(idx):
        if liquidated_on is not None:
            eq.append(0.0), expo.append(0.0)
            continue
        if cur_day != ts.date():
            day_start_eq, cur_day = equity_prev, ts.date()

        # ---- funding at the settlement hours, on positions carried into this bar
        if ts.hour in FUNDING_HOURS and pos:
            for s, p in pos.items():
                pay = p["sign"] * p["qty"] * ohlc[s]["open"][i] * cfg.funding_8h
                wallet -= pay
                funding_paid += pay

        # ---- exits on this bar for positions opened at an earlier close
        for s in list(pos):
            p = pos[s]
            o, h, l, c = (ohlc[s][k][i] for k in ("open", "high", "low", "close"))
            kind = ref = None
            if p["sign"] > 0:
                if l <= p["stop"] * (1 + EPS):
                    kind, ref = "stop", min(p["stop"], o)
                elif h >= p["tp"] * (1 - EPS):
                    kind, ref = "take_profit", o if o >= p["tp"] else p["tp"]
            else:
                if h >= p["stop"] * (1 - EPS):
                    kind, ref = "stop", max(p["stop"], o)
                elif l <= p["tp"] * (1 + EPS):
                    kind, ref = "take_profit", o if o <= p["tp"] else p["tp"]
            if kind is None and i - p["i"] >= cfg.horizon_bars:
                kind, ref = "timeout", c
            if kind:
                close_out(s, p, kind, ref, ts, i)

        # ---- liquidation test at the worst price of the bar for every remaining position at once
        if pos:
            adverse = {s: (ohlc[s]["low"][i] if p["sign"] > 0 else ohlc[s]["high"][i]) for s, p in pos.items()}
            worst_eq = wallet + sum(p["sign"] * (adverse[s] - p["fill"]) * p["qty"] for s, p in pos.items())
            worst_notional = sum(p["qty"] * adverse[s] for s, p in pos.items())
            if worst_eq <= L.MAINTENANCE_MARGIN * worst_notional:
                violations.append(f"{ts:%Y-%m-%d %H:%M} liquidated: equity {worst_eq:.2f} against maintenance {L.MAINTENANCE_MARGIN * worst_notional:.2f}")
                liquidated_on, wallet, pos = ts, 0.0, {}
                eq.append(0.0), expo.append(0.0)
                continue

        marks = {s: ohlc[s]["close"][i] for s in syms}
        unreal = sum(p["sign"] * (marks[s] - p["fill"]) * p["qty"] for s, p in pos.items())
        equity = wallet + unreal
        peak = max(peak, equity)
        latched = halted_on is not None
        if not latched and (peak - equity) / peak >= lim.account_drawdown_halt:
            halted_on, latched = ts, True

        # ---- entries at this close, each through the real gate
        for s in syms:
            d, sf = int(sig[s][0].iloc[i]), float(sig[s][1].iloc[i])
            if s in pos or d == 0 or not np.isfinite(sf) or sf <= 0 or (d > 0 and not allow_longs) or (d < 0 and not allow_shorts):
                continue
            signal_bars[s] += 1
            c = marks[s]
            cash_view = wallet - sum(q["qty"] * q["fill"] for q in pos.values() if q["sign"] > 0)      # only used when the account is spot-equivalent
            state = PortfolioState(
                now=ts, equity=equity, cash=cash_view, peak_equity=peak, day_start_equity=day_start_eq,
                positions={k: Position(k, q["qty"], q["fill"], q["stop"], q["tp"], "r", q["day"], "long" if q["sign"] > 0 else "short") for k, q in pos.items()},
                prices={k: (marks[k], 0.0, "1h") for k in syms}, halt_latched=latched, limits_ok=True)
            stop_px = c * (1 - sf) if d > 0 else c * (1 + sf)
            tp_px = c * (1 + cfg.rr * sf) if d > 0 else c * (1 - cfg.rr * sf)
            intent = OrderIntent(s, "buy" if d > 0 else "short", stop_price=stop_px, take_profit=tp_px, source="futures_replay")
            verdict = evaluate(intent, state, lim, costs=cfg.costs)
            if not verdict.approved:
                rejections[next((n for n, ok, _ in verdict.checks if not ok), "unknown")] += 1
                continue
            fill = c * (1 + slip) if d > 0 else c * (1 - slip)
            entry_fee = verdict.qty * fill * fee
            exposure_after = state.exposure + verdict.qty * c
            step = DEFAULT_RULES[s].step
            if verdict.risk_amount > equity * lim.risk_per_trade + 1e-9:
                violations.append(f"{ts:%Y-%m-%d %H:%M} {s}: risk {verdict.risk_amount:.4f} above {lim.risk_per_trade:.2%} of equity {equity:.2f}")
            if exposure_after > lim.max_exposure_fraction * equity + 1e-6:
                violations.append(f"{ts:%Y-%m-%d %H:%M} {s}: exposure {exposure_after / equity:.2f}x above the {lim.max_exposure_fraction:g}x cap")
            if exposure_after > lim.max_leverage * equity + 1e-6:
                violations.append(f"{ts:%Y-%m-%d %H:%M} {s}: leverage {exposure_after / equity:.2f}x above the {lim.max_leverage:g}x limit")
            if abs(verdict.qty / step - round(verdict.qty / step)) > 1e-6 or verdict.qty * c < DEFAULT_RULES[s].min_notional - 1e-9:
                violations.append(f"{ts:%Y-%m-%d %H:%M} {s}: quantity {verdict.qty} breaks the exchange step or minimum")
            if latched:
                violations.append(f"{ts:%Y-%m-%d %H:%M} {s}: entered while the drawdown halt was latched")
            wallet -= entry_fee
            pos[s] = {"qty": verdict.qty, "fill": fill, "stop": stop_px, "tp": tp_px, "i": i, "day": ts, "fee": entry_fee, "risk": verdict.risk_amount, "sign": d}

        unreal = sum(p["sign"] * (marks[s] - p["fill"]) * p["qty"] for s, p in pos.items())
        equity = wallet + unreal
        eq.append(equity)
        expo.append(sum(p["qty"] * marks[s] for s, p in pos.items()) / equity if equity > 0 else 0.0)
        equity_prev = equity

    return FuturesResult(pd.Series(eq, index=idx), pd.DataFrame(trades), rejections, violations, halted_on, liquidated_on, funding_paid, dict(signal_bars),
                         pd.Series(expo, index=idx), cfg)


# ---------------------------------------------------------------------------------------------------------------- the pre-registered study

PREREG = "docs/preregistration-futures-breakout.md"
VARIANTS = {                      # name: (exposure cap = leverage limit, longs, shorts, description)
    "F0": (3.0, True, False, "long only, up to 3x"),
    "F1": (1.0, True, True, "long and short, no leverage"),
    "F2": (3.0, True, True, "long and short, up to 3x (primary)"),
}


def what_if_limits(leverage: float) -> L.Limits:
    """The study's limits: NOT approved by the owner, never written to config/limits.toml."""
    return L.Limits("what-if", leverage, 0.30, 0.055, "what-if", 0.02, leverage, True)


def study(register: bool = True, require_prereg: bool = True, bars: dict | None = None) -> dict:
    from ..eval import metrics, trials
    from ..eval.channel_ablation import prereg_events, prereg_hash
    from ..eval.data import load_bars
    from ..obs.events import emit

    h = prereg_hash(PREREG) if require_prereg else None
    if require_prereg and h not in {e.get("sha256") for e in prereg_events()}:
        raise RuntimeError("the futures pre-registration does not match any logged hash: run `getrich preregister docs/preregistration-futures-breakout.md`")
    bars = bars or {s: load_bars(s, "1h") for s in SYMBOLS}
    runs: dict[str, dict] = {}
    for name, (lev, longs, shorts, _d) in VARIANTS.items():
        lim = what_if_limits(lev)
        runs[name] = {}
        for label, mult, fmult in (("base", 1.0, 1.0), ("2x", 2.0, 1.0), ("stress", 2.0, 3.0)):
            cfg = FuturesConfig(limits=lim, costs=CostModel().stressed(mult) if mult != 1.0 else CostModel(), funding_8h=FUNDING_8H * fmult)
            runs[name][label] = run(bars, cfg, allow_longs=longs, allow_shorts=shorts)
    first = runs["F2"]["base"].trades["entry"].min().floor("D") if not runs["F2"]["base"].trades.empty else runs["F2"]["base"].equity.index[0]

    def win(r: FuturesResult) -> pd.Series:
        d = r.daily_returns()
        return d[d.index >= first]

    known = {e["name"] for e in trials.load()}
    base_sh = {k: float(win(runs[k]["base"]).mean() / win(runs[k]["base"]).std(ddof=1)) if win(runs[k]["base"]).std(ddof=1) > 0 else 0.0 for k in VARIANTS}
    fresh = [v for k, v in base_sh.items() if f"futures-breakout:{k}" not in known]
    all_trials = trials.period_sharpes() + fresh
    rows = {}
    for k in VARIANTS:
        rb, r2, rs = win(runs[k]["base"]), win(runs[k]["2x"]), win(runs[k]["stress"])
        mid = r2.index[len(r2) // 2]
        tr_b, tr_2 = runs[k]["base"].trades, runs[k]["2x"].trades
        short_pnl_2x = float(tr_2.loc[tr_2["side"] == "short", "pnl"].sum()) if not tr_2.empty else 0.0
        long_pnl_2x = float(tr_2.loc[tr_2["side"] == "long", "pnl"].sum()) if not tr_2.empty else 0.0
        years = {int(y): float((1 + g).prod() - 1) for y, g in rb.groupby(rb.index.year)}
        rows[k] = {"trades": len(tr_b), "win_rate": float((tr_b["pnl"] > 0).mean()) if len(tr_b) else 0.0, "avg_r": float(tr_b["r"].mean()) if len(tr_b) else 0.0,
                   "total": float((1 + rb).prod() - 1), "cagr": metrics.cagr(rb), "sharpe": metrics.sharpe(rb), "sharpe_2x": metrics.sharpe(r2), "sharpe_stress": metrics.sharpe(rs),
                   "max_dd": metrics.max_drawdown(rb), "dsr": metrics.deflated_sharpe(rb, all_trials), "half1_2x": metrics.sharpe(r2[r2.index < mid]), "half2_2x": metrics.sharpe(r2[r2.index >= mid]),
                   "short_pnl_2x": short_pnl_2x, "long_pnl_2x": long_pnl_2x, "funding": runs[k]["base"].funding_paid, "fees": float(tr_b["fees"].sum()) if len(tr_b) else 0.0,
                   "exposure": float(runs[k]["base"].exposure[runs[k]["base"].exposure.index >= first].mean()),
                   "halted": any(runs[k][x].halted_on is not None for x in runs[k]), "halted_on": runs[k]["base"].halted_on, "liquidated": any(runs[k][x].liquidated_on is not None for x in runs[k]),
                   "violations": sum(len(runs[k][x].violations) for x in runs[k]), "rejections": dict(runs[k]["base"].rejections), "signals": runs[k]["base"].signal_bars, "years": years}
    f2 = rows["F2"]
    crit = {"sharpe_2x_at_least_1": f2["sharpe_2x"] >= 1.0, "dsr": f2["dsr"] >= 0.90, "drawdown_and_no_halt": f2["max_dd"] <= 0.30 and not f2["halted"],
            "both_halves_positive": f2["half1_2x"] > 0 and f2["half2_2x"] > 0, "funding_stress_positive": f2["sharpe_stress"] > 0, "enough_trades": f2["trades"] >= 150,
            "shorts_carry_weight": f2["short_pnl_2x"] > 0, "clean": f2["violations"] == 0 and not f2["liquidated"]}
    f2["criteria"], f2["shows_value"] = crit, all(crit.values())
    if register:
        for k in VARIANTS:
            trials.register(4, f"futures-breakout:{k}", rows[k]["sharpe"], "docs/phase5-futures-breakout.md")
    emit("eval.futures_study_run", service="eval", prereg_sha256=h, n_trials=len(all_trials), shows_value=f2["shows_value"])
    return {"rows": rows, "prereg": h, "n_trials": len(all_trials), "start": first, "end": runs["F2"]["base"].equity.index[-1]}


def study_markdown(res: dict) -> str:
    rows, f2 = res["rows"], res["rows"]["F2"]

    def pct(x):
        return f"{x * 100:+.1f}%"

    lines = ["# Hourly breakout day trading, long and short, with leverage (pre-registered)", "",
             f"Pre-registration: `{PREREG}`, SHA-256 `{(res['prereg'] or 'unchecked')[:16]}...` (matches the hash logged before the run). Window {res['start']:%Y-%m-%d} to {res['end']:%Y-%m-%d} on hourly BTCUSDT and ETHUSDT bars; start equity $500; "
             f"what-if limits (30% drawdown halt, 5.5% daily halt, 2% risk per trade; NOT approved). Costs 10 + 5 bps per side (2x also run); funding ASSUMED 0.01% per 8 hours (3x also run). Deflated Sharpe counts {res['n_trials']} trials.", "",
             "| | Trades | Win rate | Avg R | Total | CAGR | Sharpe | at 2x costs | 2x + 3x funding | Max DD | Deflated Sharpe | Avg exposure |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, (_lev, _l, _s, desc) in VARIANTS.items():
        r = rows[k]
        lines.append(f"| {k}: {desc} | {r['trades']} | {r['win_rate']:.0%} | {r['avg_r']:+.2f} | {pct(r['total'])} | {r['cagr'] * 100:.1f}% | {r['sharpe']:.2f} | {r['sharpe_2x']:.2f} | {r['sharpe_stress']:.2f} | {r['max_dd'] * 100:.1f}% | {r['dsr']:.3f} | {r['exposure'] * 100:.0f}% |")
    lines += ["", "## What each part contributed (2x costs, dollars on a $500 start)", "", "| | Long trades P&L | Short trades P&L | Fees (base) | Net funding paid (base) | Halt tripped | Liquidated | Violations |", "|---|---:|---:|---:|---:|---|---|---:|"]
    for k in VARIANTS:
        r = rows[k]
        lines.append(f"| {k} | {r['long_pnl_2x']:+.0f} | {r['short_pnl_2x']:+.0f} | {r['fees']:.0f} | {r['funding']:+.1f} | {'yes' if r['halted'] else 'no'} | {'yes' if r['liquidated'] else 'no'} | {r['violations']} |")
    lines += ["", "The drawdown halt latches until the owner resets it (`unhalt`), and this replay never resets it, so after it trips a variant takes no new trades for the rest of the window. "
              "Halt tripped on (base costs): " + ", ".join(f"{k} {rows[k]['halted_on']:%Y-%m-%d}" if rows[k]["halted_on"] is not None else f"{k} never" for k in VARIANTS) + ". "
              "Years after that date show 0.0% because nothing was traded, not because the rule was tested and found flat."]
    years = sorted({y for r in rows.values() for y in r["years"]})
    lines += ["", "## By calendar year (base costs)", "", "| Year | " + " | ".join(VARIANTS) + " |", "|---|" + "---:|" * len(VARIANTS)]
    for y in years:
        lines.append(f"| {y} | " + " | ".join(pct(rows[k]["years"].get(y, 0.0)) for k in VARIANTS) + " |")
    lines += ["", "## Gate rejections of F2 signals (base costs)", "", ", ".join(f"{n}: {c}" for n, c in sorted(rows["F2"]["rejections"].items(), key=lambda kv: -kv[1])) or "none", "",
              f"Signals seen: {rows['F2']['signals']}.", "", "## Pre-registered criteria for F2", ""]
    names = {"sharpe_2x_at_least_1": "Sharpe at 2x costs at least 1.0", "dsr": "Deflated Sharpe at least 0.90", "drawdown_and_no_halt": "max drawdown at most 30% and the halt never trips",
             "both_halves_positive": "Sharpe at 2x costs positive in both halves", "funding_stress_positive": "Sharpe positive at 2x costs with 3x funding", "enough_trades": "at least 150 trades",
             "shorts_carry_weight": "short trades profitable at 2x costs", "clean": "no violations, no liquidation"}
    for k, ok in f2["criteria"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'}: {names[k]}")
    lines += ["", f"**Verdict: F2 {'SHOWS VALUE' if f2['shows_value'] else 'NOT SHOWN'}.**", "",
              "Caveats: one in-sample path; funding and maintenance margin are assumptions; perpetual basis ignored; fills at the close or the stop level with no queue or partial fills; a gap through a stop is the loss leverage multiplies and no stop can prevent."]
    return "\n".join(lines) + "\n"
