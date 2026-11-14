"""The risk gate: a pure, deterministic function. No network, no database, no clock of its own, no randomness.

It can tighten a request (smaller size, or no) but never loosen one: the approved quantity is never above what was asked
for or what the risk budget allows. Exits that reduce a position are always allowed, including when halted or killed, so
that nothing can trap the account in a position.

Spot, long-only: a buy opens a position, a sell can only reduce one. One position per symbol.
"""

from __future__ import annotations

import math

from ..eval.costs import CostModel
from . import limits as L
from .types import DEFAULT_RULES, OrderIntent, PortfolioState, SymbolRules, Verdict

FEE_RESERVE = 0.003        # keep cash for fees and slippage on the way in


def _floor_to(x: float, step: float) -> float:
    return math.floor(round(x / step, 9)) * step if step > 0 else x


def evaluate(intent: OrderIntent, state: PortfolioState, limits: L.Limits | None, rules: dict[str, SymbolRules] | None = None,
             costs: CostModel | None = None) -> Verdict:
    rules, costs = rules or DEFAULT_RULES, costs or CostModel()
    v = Verdict(approved=False)

    def check(name: str, ok: bool, detail: str) -> bool:
        v.checks.append((name, ok, detail))
        if not ok:
            v.reasons.append(f"{name}: {detail}")
        return ok

    side = intent.side.lower()
    if side not in ("buy", "sell"):
        check("side", False, f"unknown side {intent.side!r}")
        return v
    if not check("symbol", intent.symbol in rules, f"{intent.symbol} is not tradable here (known: {sorted(rules)})"):
        return v
    sym_rules = rules[intent.symbol]
    px_info = state.prices.get(intent.symbol)
    pos = state.positions.get(intent.symbol)

    # ---- exits: reduce-only, always allowed, never sized up
    if side == "sell":
        if not check("reduce_only", pos is not None and pos.qty > 0, "no open position to sell (spot is long-only)"):
            return v
        qty = pos.qty if intent.qty is None else min(intent.qty, pos.qty)
        qty = _floor_to(qty, sym_rules.step)
        if not check("quantity", qty >= sym_rules.min_qty, f"quantity {qty} is below the exchange minimum {sym_rules.min_qty}"):
            return v
        price = px_info[0] if px_info else pos.avg_price
        v.approved, v.qty, v.notional = True, qty, qty * price
        v.checks.append(("exit_always_allowed", True, "reducing a position is allowed even when halted or killed"))
        return v

    # ---- entries
    if not check("kill_switch", not state.killed, "the kill switch is on: no new positions until `unkill`"):
        return v
    if not check("limits_pinned", state.limits_ok and limits is not None, state.limits_detail or "limits unavailable"):
        return v
    if not check("halt_latch", not state.halt_latched, "the account drawdown halt tripped earlier and has not been reset: review, then run `getrich unhalt`"):
        v.halted = True
        return v
    dd = (state.peak_equity - state.equity) / state.peak_equity if state.peak_equity > 0 else 0.0
    if dd >= limits.account_drawdown_halt:
        v.halted = True
    if not check("account_drawdown_halt", dd < limits.account_drawdown_halt,
                 f"drawdown {dd:.1%} has reached the {limits.account_drawdown_halt:.0%} halt: no new positions until the owner resets it"):
        return v
    day = (state.day_start_equity - state.equity) / state.day_start_equity if state.day_start_equity > 0 else 0.0
    if not check("daily_loss_halt", day < limits.daily_loss_halt, f"today's loss {day:.1%} has reached the {limits.daily_loss_halt:.1%} halt: no new positions until tomorrow (UTC)"):
        return v
    if not check("one_position_per_symbol", pos is None, f"already holding {pos.qty if pos else 0} {intent.symbol}; adding to a position is not allowed"):
        return v

    # price: a known, fresh bar. Stale prices mean a stale decision.
    if not check("price_known", px_info is not None, f"no stored bars for {intent.symbol}"):
        return v
    price, age_s, tf = px_info
    max_age = 3 * 3600 if tf == "1h" else 36 * 3600
    if not check("price_fresh", age_s <= max_age, f"latest {tf} bar is {age_s / 3600:.1f}h old (limit {max_age / 3600:.0f}h): collector may be down"):
        return v

    # stop
    stop = intent.stop_price
    if not check("stop_required", stop is not None and stop > 0, "a buy needs a stop price"):
        return v
    if not check("stop_below_price", stop < price, f"stop {stop} must be below the current price {price}"):
        return v
    stop_frac = (price - stop) / price
    if not check("stop_distance", L.MIN_STOP_FRACTION <= stop_frac <= L.MAX_STOP_FRACTION,
                 f"stop is {stop_frac:.2%} below price; allowed range is {L.MIN_STOP_FRACTION:.1%} to {L.MAX_STOP_FRACTION:.0%}"):
        return v
    if intent.take_profit is not None and not check("take_profit_above_price", intent.take_profit > price, "take profit must be above the current price"):
        return v

    # cost gate
    cost_r = costs.cost_in_r(stop_frac)
    if not check("cost_gate", cost_r <= L.MAX_COST_R,
                 f"round-trip costs are {cost_r:.2f}R for a {stop_frac:.2%} stop (limit {L.MAX_COST_R}R): the stop is too tight for the costs"):
        return v
    if intent.expected_edge_fraction is not None and not check(
            "edge_beats_costs", intent.expected_edge_fraction >= L.EDGE_COST_MULTIPLE * costs.round_trip(),
            f"claimed edge {intent.expected_edge_fraction:.2%} is under {L.EDGE_COST_MULTIPLE:g}x round-trip cost {costs.round_trip():.2%}"):
        return v

    # conduct guard: cancels per fill
    ratio = state.cancels_24h / max(state.fills_24h, 1)
    if not check("conduct_cancel_to_fill", state.cancels_24h < 3 or ratio <= L.MAX_CANCEL_TO_FILL,
                 f"{state.cancels_24h} cancels against {state.fills_24h} fills in 24h exceeds {L.MAX_CANCEL_TO_FILL:g}:1"):
        return v

    # sizing: the smallest of every constraint, never above the request
    risk_frac = min(L.RISK_PER_TRADE, intent.risk_fraction) if intent.risk_fraction else L.RISK_PER_TRADE
    risk_budget = state.equity * risk_frac
    caps = {"risk budget": risk_budget / (price - stop),
            "exposure cap": (limits.max_exposure_fraction * state.equity - state.exposure) / price,
            "cash": state.cash / (price * (1 + FEE_RESERVE))}
    if intent.qty is not None:
        caps["requested quantity"] = intent.qty
    binding = min(caps, key=caps.get)
    qty = _floor_to(caps[binding], sym_rules.step)
    v.checks.append(("sizing", True, f"limited by {binding}: " + ", ".join(f"{k} {c:.6g}" for k, c in caps.items())))
    if not check("exposure_room", caps["exposure cap"] > 0, f"exposure {state.exposure / state.equity:.1%} already at the {limits.max_exposure_fraction:.0%} cap"):
        return v
    if not check("quantity", qty >= sym_rules.min_qty and qty * price >= sym_rules.min_notional,
                 f"the allowed size {qty:.6g} (~{qty * price:.2f}) is under the exchange minimum ({sym_rules.min_qty} / {sym_rules.min_notional} notional); "
                 f"the minimum would overshoot the {binding} limit"):
        return v
    if binding != "requested quantity" and intent.qty is not None and qty < intent.qty:
        v.reasons.append(f"size reduced from {intent.qty:g} to {qty:g} by the {binding}")

    v.approved, v.qty, v.notional = True, qty, qty * price
    v.risk_amount = qty * (price - stop)
    v.risk_fraction = v.risk_amount / state.equity if state.equity > 0 else 0.0
    return v
