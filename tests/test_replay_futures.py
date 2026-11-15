"""The margin replay engine: shorts profit when price falls, leverage is capped, funding and liquidation behave, and nothing slips past the gate."""

import numpy as np
import pandas as pd
import pytest

from getrich.trading import limits as L
from getrich.trading import replay_futures as rf


def lim(**kw):
    base = dict(profile="test", max_exposure_fraction=2.0, account_drawdown_halt=0.5, daily_loss_halt=0.5, sha256="x", risk_per_trade=0.02, max_leverage=3.0, allow_short=True)
    base.update(kw)
    return L.Limits(**base)


def bars(closes, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="h", tz="UTC")
    c = np.array(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.0005, "low": np.minimum(o, c) * 0.9995, "close": c}, index=idx)


def one_signal(direction, at, stop=0.02):
    def strat(px):
        d = pd.Series(0, index=px.index)
        d.iloc[at] = direction
        return d, pd.Series(stop, index=px.index)
    return strat


def cfg(**kw):
    return rf.FuturesConfig(limits=kw.pop("limits", lim()), symbols=("BTCUSDT",), **kw)


def run(closes, direction, at=3, stop=0.02, **kw):
    return rf.run({"BTCUSDT": bars(closes)}, cfg(**kw), one_signal(direction, at, stop))


def test_a_short_makes_money_when_price_falls_to_the_take_profit():
    closes = [100] * 4 + list(np.linspace(100, 90, 8)) + [90] * 8
    r = run(closes, -1)
    t = r.trades.iloc[0]
    assert t["side"] == "short" and t["kind"] == "take_profit" and t["pnl"] > 0
    assert r.equity.iloc[-1] > 500 and not r.violations


def test_a_short_loses_when_price_rises_through_the_stop_and_the_loss_is_about_the_risk():
    closes = [100] * 4 + list(np.linspace(100, 108, 8)) + [108] * 8
    r = run(closes, -1)
    t = r.trades.iloc[0]
    assert t["kind"] == "stop" and t["pnl"] < 0
    assert -t["pnl"] == pytest.approx(t["risk"], rel=0.5)        # stop fills near the stop; costs add a little
    assert abs(t["r"]) < 2.5


def test_a_long_works_the_same_way_and_leverage_is_never_above_the_limit():
    closes = [100] * 4 + list(np.linspace(100, 112, 10)) + [112] * 6
    r = run(closes, 1, limits=lim(risk_per_trade=0.05, max_exposure_fraction=2.0))
    t = r.trades.iloc[0]
    assert t["side"] == "long" and t["pnl"] > 0
    assert t["notional"] <= 2.0 * 500 * 1.001            # the cap is measured at the close; the fill adds slippage (5 bps)
    assert not r.violations


def test_funding_is_paid_by_longs_and_received_by_shorts():
    flat = [100] * 60
    long_ = run(flat, 1, at=1, funding_8h=0.001)
    short_ = run(flat, -1, at=1, funding_8h=0.001)
    assert long_.funding_paid > 0 > short_.funding_paid
    assert long_.trades.iloc[0]["kind"] == "timeout"


def test_shorting_off_means_no_short_entries():
    r = run([100] * 30, -1, limits=lim(allow_short=False))
    assert r.trades.empty and r.rejections["shorting_allowed"] == 1


def test_a_stop_tighter_than_the_cost_gate_allows_is_rejected_not_traded():
    r = run([100] * 30, 1, stop=0.006)
    assert r.trades.empty and r.rejections["cost_gate"] == 1


def test_a_gap_through_the_stop_fills_at_the_worse_open_and_can_exceed_the_risk():
    c = [100] * 4 + [100, 100, 100] + [90] * 20
    b = bars(c)
    b.loc[b.index[7], "open"] = 90.0                                  # gaps 10% below a 2% stop
    b.loc[b.index[7], "high"] = 90.5
    r = rf.run({"BTCUSDT": b}, cfg(), one_signal(1, 3))
    t = r.trades.iloc[0]
    assert t["kind"] == "stop" and t["r"] < -3                         # a gap is the loss a stop cannot prevent


def test_the_drawdown_halt_blocks_new_entries_after_it_trips():
    c = [100] * 4 + list(np.linspace(100, 70, 20)) + [70] * 40

    def strat(px):
        d = pd.Series(0, index=px.index)
        d.iloc[3] = 1
        d.iloc[35] = 1
        return d, pd.Series(0.02, index=px.index)
    r = rf.run({"BTCUSDT": bars(c)}, cfg(limits=lim(account_drawdown_halt=0.04, risk_per_trade=0.05)), strat)
    assert r.halted_on is not None
    assert len(r.trades) == 1 and r.rejections["halt_latch"] + r.rejections["account_drawdown_halt"] >= 1
    assert not r.violations


def test_the_breakout_rule_goes_long_in_an_uptrend_and_short_in_a_downtrend_with_a_floor_on_the_stop():
    rng = np.random.default_rng(0)
    up = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.003, 0.004, 400))))
    down = pd.Series(100 * np.exp(np.cumsum(rng.normal(-0.003, 0.004, 400))))
    for series, want in ((up, 1), (down, -1)):
        px = bars(series.to_numpy())
        d, stop = rf.breakout_signals(px)
        assert (d == want).sum() > 5 and (d == -want).sum() == 0
        assert (stop.dropna() >= rf.STOP_FLOOR - 1e-12).all()


def test_the_breakout_rule_uses_only_past_data():
    rng = np.random.default_rng(1)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, 300)))
    full = rf.breakout_signals(bars(c))
    cut = rf.breakout_signals(bars(c[:200]))
    assert (full[0].iloc[:200].to_numpy() == cut[0].to_numpy()).all()
    assert np.allclose(full[1].iloc[:200].to_numpy(), cut[1].to_numpy(), equal_nan=True)


def test_equity_matches_cash_flows_when_there_are_no_costs():
    from getrich.eval.costs import CostModel
    closes = [100] * 4 + list(np.linspace(100, 90, 8)) + [90] * 8
    r = run(closes, -1, costs=CostModel(0.0, 0.0), funding_8h=0.0)
    t = r.trades.iloc[0]
    assert r.equity.iloc[-1] == pytest.approx(500 + t["pnl"], rel=1e-9)
