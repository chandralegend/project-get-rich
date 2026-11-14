import numpy as np
import pandas as pd
import pytest

from getrich.eval.costs import CostModel
from getrich.trading import limits as L
from getrich.trading.replay import ReplayConfig, run

LIM = L.Limits("minimal", 0.2, 0.15, 0.025, "x")


def bars_from(close, spread=0.01):
    idx = pd.date_range("2020-01-01", periods=len(close), freq="D", tz="UTC")
    c = np.asarray(close, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + spread), "low": np.minimum(o, c) * (1 - spread), "close": c, "volume": 1.0}, index=idx)


def walk(n=700, drift=0.002, vol=0.02, seed=0, start=100.0):
    rng = np.random.default_rng(seed)
    return start * np.cumprod(1 + rng.normal(drift, vol, n))


def two(seed=0, **kw):
    return {"BTCUSDT": bars_from(walk(seed=seed, start=60000.0, **kw)), "ETHUSDT": bars_from(walk(seed=seed + 1, start=2000.0, **kw))}


def test_invariants_hold_over_many_random_histories():
    for seed in range(6):
        for drift in (0.003, 0.0, -0.002):
            res = run(two(seed, drift=drift, vol=0.03), ReplayConfig(limits=LIM))
            assert res.violations == [], (seed, drift, res.violations[:2])
            assert (res.equity > 0).all()


def test_an_uptrend_is_entered_and_never_more_than_one_position_per_symbol():
    res = run(two(drift=0.004), ReplayConfig(limits=LIM))
    assert len(res.trades) > 5
    for s, g in res.trades.groupby("symbol"):
        g = g.sort_values("entry")
        assert (g["entry"].iloc[1:].to_numpy() >= g["exit"].iloc[:-1].to_numpy()).all()       # a position closes before the next one opens


def test_risk_per_trade_and_exposure_are_bounded_on_every_trade():
    res = run(two(drift=0.004, vol=0.025), ReplayConfig(limits=LIM))
    for _, t in res.trades.iterrows():                       # equity on the entry day, after fees: within a fraction of a percent of what the gate saw
        assert t.risk <= 0.005 * res.equity.loc[t.entry] * 1.003
    # the cap binds when a position is opened (the replay itself checks that on every entry); a winner can then drift above it as its price rises
    assert res.exposure.max() <= LIM.max_exposure_fraction * 1.5


def test_trade_pnl_is_price_move_minus_fees_and_costs_reduce_results():
    cheap = run(two(drift=0.003), ReplayConfig(limits=LIM, costs=CostModel(0.0, 0.0)))
    base = run(two(drift=0.003), ReplayConfig(limits=LIM))
    dear = run(two(drift=0.003), ReplayConfig(limits=LIM, costs=CostModel().stressed(2.0)))
    assert cheap.equity.iloc[-1] > base.equity.iloc[-1] > dear.equity.iloc[-1]
    t = base.trades.iloc[0]
    assert t.pnl == pytest.approx((t.exit_px - t.entry_px) * t.qty - t.fees)
    assert cheap.trades.fees.sum() == pytest.approx(0.0)


def test_a_gap_down_through_the_stop_exits_at_the_worse_open():
    rng = np.random.default_rng(3)
    up = 100 * np.cumprod(1 + rng.normal(0.004, 0.02, 420))
    gapped = up[-1] * 0.6
    path = np.concatenate([up, [gapped], np.full(10, gapped)])
    btc = bars_from(path, spread=0.0)
    btc.iloc[420, btc.columns.get_loc("open")] = gapped                                             # a true gap: the bar opens at the new level
    eth = bars_from(path * 3, spread=0.0)
    eth.iloc[420, eth.columns.get_loc("open")] = gapped * 3
    res = run({"BTCUSDT": btc, "ETHUSDT": eth}, ReplayConfig(limits=LIM))
    gap_day = res.equity.index[420]
    hit = res.trades[(res.trades.exit == gap_day) & (res.trades.kind == "stop") & (res.trades.symbol == "BTCUSDT")]
    assert len(hit) == 1
    assert hit.exit_px.iloc[0] == pytest.approx(gapped * (1 - 0.0005))                              # the gapped open less slippage, far below the 2-sigma stop
    assert hit.pnl.iloc[0] < -hit.risk.iloc[0]                                                      # the loss is bigger than the risk budget: that is what a gap does
    assert res.violations == []


def test_the_drawdown_halt_stops_new_entries_for_good():
    tight = L.Limits("t", 0.2, 0.002, 0.025, "x")                                                    # a halt at 0.2% trips after one small loss
    res = run(two(drift=-0.003, vol=0.03), ReplayConfig(limits=tight))
    assert res.halted_on is not None and res.violations == []
    assert (res.trades.entry <= res.halted_on).all()                                                 # nothing opened after the halt
    assert res.rejections["halt_latch"] + res.rejections["account_drawdown_halt"] > 0


def test_the_replay_is_deterministic():
    a, b = run(two(), ReplayConfig(limits=LIM)), run(two(), ReplayConfig(limits=LIM))
    pd.testing.assert_series_equal(a.equity, b.equity)
    pd.testing.assert_frame_equal(a.trades, b.trades)
