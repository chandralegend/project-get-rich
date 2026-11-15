"""Replay stored history through the REAL order path: the same risk gate, cost model and approved limits that paper and testnet use.

What it is for: showing, on years of real prices, that the gated system behaves (never exceeds a risk or exposure limit,
sizes correctly, pays costs, respects halts) and what a gated strategy actually earns. It is not a tuning tool.

Strategy (fixed in advance, the pre-registered Phase 3 primary rule, nothing tuned on this replay):
  enter long at the close of a day when at least 2/3 of the three EMA trend pairs vote up and the symbol is flat;
  stop 2 sigma below, take profit 4 sigma above (sigma = 20-day EWMA daily volatility), sell at the close after 20 days;
  one position per symbol; every entry goes through gate.evaluate and is sized by it.

Timing follows the research backtest: decide at the close of day t with data up to t, fill at that close (plus the
cost model's slippage), then stops and take profits are tested against the following bars (a gap fills at the worse
open; a bar touching both stop and take profit counts as the stop).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..eval import baselines
from ..eval.costs import CostModel
from ..eval.labels import EPS, daily_vol
from . import limits as L
from .gate import evaluate
from .types import DEFAULT_RULES, OrderIntent, PortfolioState, Position

SYMBOLS = ("BTCUSDT", "ETHUSDT")


@dataclass(frozen=True)
class ReplayConfig:
    limits: L.Limits
    start_equity: float = 500.0
    min_votes: float = 2 / 3
    sl_mult: float = 2.0
    tp_mult: float = 4.0
    horizon: int = 20
    costs: CostModel = field(default_factory=CostModel)
    symbols: tuple[str, ...] = SYMBOLS


@dataclass
class ReplayResult:
    equity: pd.Series
    trades: pd.DataFrame
    rejections: Counter
    violations: list[str]
    halted_on: pd.Timestamp | None
    signal_days: dict[str, int]
    exposure: pd.Series
    config: ReplayConfig

    @property
    def returns(self) -> pd.Series:
        return self.equity.pct_change().fillna(0.0)


def run(bars: dict[str, pd.DataFrame], cfg: ReplayConfig) -> ReplayResult:
    syms = [s for s in cfg.symbols if s in bars]
    idx = bars[syms[0]].index
    for s in syms[1:]:
        idx = idx.intersection(bars[s].index)
    px = {s: bars[s].reindex(idx) for s in syms}
    votes = {s: baselines.trend_signal(px[s]["close"]) for s in syms}
    sigma = {s: daily_vol(px[s]["close"]) for s in syms}
    slip, fee = cfg.costs.slippage_bps / 1e4, cfg.costs.fee_bps / 1e4

    cash, equity_prev, peak, halted_on = cfg.start_equity, cfg.start_equity, cfg.start_equity, None
    pos: dict[str, dict] = {}
    trades, violations, rejections = [], [], Counter()
    signal_days = Counter()
    eq, expo = [], []

    for i, day in enumerate(idx):
        # ---- exits on this bar for positions opened at an earlier close
        for s in list(pos):
            p, o, h, l, c = pos[s], *(float(px[s][k].iloc[i]) for k in ("open", "high", "low", "close"))
            kind, ref = None, None
            if l <= p["stop"] * (1 + EPS):
                kind, ref = "stop", min(p["stop"], o)
            elif h >= p["tp"] * (1 - EPS):
                kind, ref = "take_profit", o if o >= p["tp"] else p["tp"]
            elif i - p["i"] >= cfg.horizon:
                kind, ref = "timeout", c
            if kind:
                fill = ref * (1 - slip)
                proceeds, exit_fee = p["qty"] * fill, p["qty"] * fill * fee
                cash += proceeds - exit_fee
                pnl = proceeds - exit_fee - p["cost"]
                trades.append({"symbol": s, "entry": p["day"], "exit": day, "days": i - p["i"], "qty": p["qty"], "entry_px": p["fill"], "exit_px": fill,
                               "kind": kind, "pnl": pnl, "risk": p["risk"], "r": pnl / p["risk"] if p["risk"] > 0 else np.nan,
                               "fees": p["fee"] + exit_fee, "notional": p["qty"] * p["fill"]})
                del pos[s]

        marks = {s: float(px[s]["close"].iloc[i]) for s in syms}
        equity = cash + sum(p["qty"] * marks[s] for s, p in pos.items())
        peak = max(peak, equity)
        latched = halted_on is not None
        if not latched and (peak - equity) / peak >= cfg.limits.account_drawdown_halt:
            halted_on, latched = day, True

        # ---- entries at this close, each through the real gate
        for s in syms:
            v, sg = votes[s].iloc[i], sigma[s].iloc[i]
            if s in pos or not np.isfinite(sg) or sg <= 0 or v < cfg.min_votes - 1e-9:
                continue
            signal_days[s] += 1
            c = marks[s]
            state = PortfolioState(
                now=day, equity=equity, cash=cash, peak_equity=peak, day_start_equity=equity_prev,
                positions={k: Position(k, q["qty"], q["fill"], q["stop"], q["tp"], "r", q["day"]) for k, q in pos.items()},
                prices={k: (marks[k], 0.0, "1d") for k in syms}, halt_latched=latched, limits_ok=True)
            intent = OrderIntent(s, "buy", stop_price=c * (1 - cfg.sl_mult * sg), take_profit=c * (1 + cfg.tp_mult * sg), source="trend_replay")
            verdict = evaluate(intent, state, cfg.limits, costs=cfg.costs)
            if not verdict.approved:
                rejections[next((n for n, ok, _ in verdict.checks if not ok), "unknown")] += 1
                continue
            fill = c * (1 + slip)
            cost = verdict.qty * fill
            entry_fee = cost * fee
            exposure_after = state.exposure + verdict.qty * c
            step = DEFAULT_RULES[s].step
            if verdict.risk_amount > equity * cfg.limits.risk_per_trade + 1e-9:
                violations.append(f"{day:%Y-%m-%d} {s}: risk {verdict.risk_amount:.4f} above {cfg.limits.risk_per_trade:.2%} of equity {equity:.2f}")
            if exposure_after > cfg.limits.max_exposure_fraction * equity + 1e-6:
                violations.append(f"{day:%Y-%m-%d} {s}: exposure {exposure_after / equity:.2%} above the {cfg.limits.max_exposure_fraction:.0%} cap")
            if abs(verdict.qty / step - round(verdict.qty / step)) > 1e-6 or verdict.qty * c < DEFAULT_RULES[s].min_notional - 1e-9:
                violations.append(f"{day:%Y-%m-%d} {s}: quantity {verdict.qty} breaks the exchange step or minimum")
            if cash - cost - entry_fee < -1e-9:
                violations.append(f"{day:%Y-%m-%d} {s}: cash would go negative")
            if latched:
                violations.append(f"{day:%Y-%m-%d} {s}: entered while the drawdown halt was latched")
            cash -= cost + entry_fee
            pos[s] = {"qty": verdict.qty, "fill": fill, "stop": intent.stop_price, "tp": intent.take_profit, "i": i, "day": day,
                      "cost": cost + entry_fee, "fee": entry_fee, "risk": verdict.risk_amount}

        equity = cash + sum(p["qty"] * marks[s] for s, p in pos.items())     # entries at the close only cost fees and slippage
        eq.append(equity)
        expo.append(sum(p["qty"] * marks[s] for s, p in pos.items()) / equity if equity > 0 else 0.0)
        equity_prev = equity

    return ReplayResult(pd.Series(eq, index=idx), pd.DataFrame(trades), rejections, violations, halted_on, dict(signal_days),
                        pd.Series(expo, index=idx), cfg)
