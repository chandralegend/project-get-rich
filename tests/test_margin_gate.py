"""Shorting and leverage in the risk gate: off by default, fail closed, and the same tighten-only rules when on."""

import pytest

from getrich.trading import gate, limits as L
from getrich.trading.types import OrderIntent, PortfolioState, Position
from getrich.obs.events import utcnow


def lim(**kw):
    base = dict(profile="test", max_exposure_fraction=2.0, account_drawdown_halt=0.30, daily_loss_halt=0.055, sha256="x", risk_per_trade=0.02, max_leverage=3.0, allow_short=True)
    base.update(kw)
    return L.Limits(**base)


def state(**over):
    base = dict(now=utcnow(), equity=500.0, cash=500.0, peak_equity=500.0, day_start_equity=500.0, positions={},
                prices={"BTCUSDT": (60000.0, 600.0, "1h"), "ETHUSDT": (2000.0, 600.0, "1h")}, limits_ok=True)
    base.update(over)
    return PortfolioState(**base)


def short(**kw):
    base = dict(symbol="BTCUSDT", side="short", stop_price=61200.0)
    base.update(kw)
    return OrderIntent(**base)


def test_shorting_is_refused_unless_the_limits_allow_it():
    v = gate.evaluate(short(), state(), lim(allow_short=False))
    assert not v.approved and any("shorting_allowed" in r for r in v.reasons)


def test_a_short_is_sized_from_the_risk_budget():
    v = gate.evaluate(short(), state(), lim())            # stop 2% above: 2% of 500 = $10 at risk -> $500 notional
    assert v.approved
    assert v.risk_amount == pytest.approx(10.0, rel=0.01)
    assert v.notional == pytest.approx(500.0, rel=0.01)
    assert v.leverage_after == pytest.approx(1.0, rel=0.02)


def test_a_short_stop_must_be_above_the_price_and_take_profit_below():
    assert not gate.evaluate(short(stop_price=58800.0), state(), lim()).approved
    assert not gate.evaluate(short(take_profit=62000.0), state(), lim()).approved
    assert gate.evaluate(short(take_profit=57000.0), state(), lim()).approved


def test_leverage_lets_the_exposure_exceed_equity_but_never_the_cap():
    v = gate.evaluate(short(stop_price=60900.0), state(), lim(max_exposure_fraction=2.0, risk_per_trade=0.05))   # 1.5% stop, 5% risk -> $1667 wanted, cap is 2x = $1000
    assert v.approved and v.notional <= 1000.0 + 1e-6
    assert v.leverage_after <= 2.0 + 1e-9
    assert "exposure cap" in next(d for n, ok, d in v.checks if n == "sizing")


def test_margin_limits_the_size_when_positions_already_use_it():
    held = {"ETHUSDT": Position("ETHUSDT", 0.5, 2000.0, 2100.0, None, "o", None, "short")}      # $1000 notional already open
    s = state(positions=held)
    v = gate.evaluate(short(), s, lim(max_exposure_fraction=3.0, max_leverage=3.0, risk_per_trade=0.05))
    assert v.approved
    assert v.notional + 1000.0 <= 3.0 * 500.0 + 1e-6


def test_the_liquidation_buffer_caps_size_for_a_wide_stop_at_high_leverage():
    v = gate.evaluate(short(stop_price=60000.0 * 1.19), state(), lim(max_exposure_fraction=10.0, max_leverage=10.0, risk_per_trade=0.05))
    assert v.approved
    assert v.liq_distance * L.LIQ_SAFETY >= 0.19 - 1e-3          # the stop sits inside half the distance to liquidation


def test_one_position_per_symbol_applies_to_shorts_too():
    held = {"BTCUSDT": Position("BTCUSDT", 0.005, 60000.0, 61200.0, None, "o", None, "short")}
    assert not gate.evaluate(short(), state(positions=held), lim()).approved
    assert not gate.evaluate(OrderIntent("BTCUSDT", "buy", 58800.0), state(positions=held), lim()).approved


def test_covering_a_short_is_always_allowed_even_halted_killed_or_with_shorting_off():
    held = {"BTCUSDT": Position("BTCUSDT", 0.005, 60000.0, 61200.0, None, "o", None, "short")}
    s = state(positions=held, killed=True, halt_latched=True)
    v = gate.evaluate(OrderIntent("BTCUSDT", "cover"), s, lim(allow_short=False))
    assert v.approved and v.qty == pytest.approx(0.005)


def test_sell_cannot_close_a_short_and_cover_cannot_close_a_long():
    short_pos = {"BTCUSDT": Position("BTCUSDT", 0.005, 60000.0, 61200.0, None, "o", None, "short")}
    long_pos = {"BTCUSDT": Position("BTCUSDT", 0.005, 60000.0, 58800.0, None, "o", None, "long")}
    assert not gate.evaluate(OrderIntent("BTCUSDT", "sell"), state(positions=short_pos), lim()).approved
    assert not gate.evaluate(OrderIntent("BTCUSDT", "cover"), state(positions=long_pos), lim()).approved


def test_default_limits_keep_the_account_spot_only():
    d = L.Limits("minimal", 0.2, 0.15, 0.025, "x")
    assert d.max_leverage == 1.0 and d.allow_short is False
    assert not gate.evaluate(short(), state(), d).approved


def test_a_long_with_leverage_can_use_more_than_cash():
    long_ = OrderIntent("BTCUSDT", "buy", 58800.0)         # 2% stop, 4% risk -> $1000 notional, twice the cash
    v = gate.evaluate(long_, state(), lim(max_exposure_fraction=2.0, max_leverage=2.0, risk_per_trade=0.04))
    assert v.approved and v.notional == pytest.approx(1000.0, rel=0.02)
    spot = gate.evaluate(long_, state(), lim(max_exposure_fraction=1.0, max_leverage=1.0, allow_short=False, risk_per_trade=0.04))
    assert spot.approved and spot.notional <= 500.0
