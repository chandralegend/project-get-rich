import numpy as np
import pandas as pd
import pytest

from getrich.eval import backtest, baselines, labels
from getrich.eval.costs import CostModel

FREE = CostModel(0, 0)
C = CostModel(fee_bps=10, slippage_bps=5)  # 30 bps round trip


def _bars(rows):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    return pd.DataFrame(rows, columns=["high", "low", "close"], index=idx)


def _sigma(bars, s=0.05):
    return pd.Series(s, index=bars.index)


def _first(bars, **kw):
    kw.setdefault("cost", FREE)
    return labels.triple_barrier(bars, _sigma(bars), horizon=3, **kw).iloc[0]


def test_take_profit_is_hit_at_the_barrier_price():
    # entry 100, 5% sigma, tp 10%: bar 1 reaches 110
    row = _first(_bars([(100, 100, 100), (110, 99, 105), (106, 100, 104), (106, 100, 104), (106, 100, 104), (106, 100, 104)]))
    assert row["exit"] == "tp" and row["r_gross"] == pytest.approx(2.0) and row["label"] == 1


def test_stop_loss_is_minus_one_r():
    row = _first(_bars([(100, 100, 100), (101, 94, 96), (106, 100, 104), (106, 100, 104), (106, 100, 104), (106, 100, 104)]))
    assert row["exit"] == "sl" and row["r_gross"] == pytest.approx(-1.0) and row["label"] == 0


def test_a_bar_touching_both_barriers_counts_as_the_stop():
    row = _first(_bars([(100, 100, 100), (111, 94, 100), (101, 99, 100), (101, 99, 100), (101, 99, 100), (101, 99, 100)]))
    assert row["exit"] == "sl"


def test_timeout_exits_at_the_horizon_close():
    row = _first(_bars([(100, 100, 100), (104, 97, 101), (104, 97, 102), (104, 97, 103), (104, 97, 103), (104, 97, 103)]))
    assert row["exit"] == "timeout" and row["bars_held"] == 3
    assert row["r_gross"] == pytest.approx(0.03 / 0.05)


def test_costs_come_off_in_r_units():
    bars = _bars([(100, 100, 100), (110, 99, 105), (106, 100, 104), (106, 100, 104), (106, 100, 104), (106, 100, 104)])
    row = _first(bars, cost=C)
    assert row["cost_r"] == pytest.approx(0.003 / 0.05)       # 0.06R
    assert row["r_net"] == pytest.approx(2.0 - 0.06)


def test_a_small_win_can_be_a_net_loss_after_costs():
    bars = _bars([(100, 100, 100), (101, 99.9, 100.1), (101, 99.9, 100.1), (101, 99.9, 100.1), (101, 99.9, 100.1), (101, 99.9, 100.1)])
    row = _first(bars, cost=C)
    assert row["r_gross"] > 0 and row["r_net"] < 0 and row["label"] == 0


def test_short_side_mirrors_the_long_side():
    tp = _first(_bars([(100, 100, 100), (101, 89, 95), (101, 95, 96), (101, 95, 96), (101, 95, 96), (101, 95, 96)]), side=-1)
    assert tp["exit"] == "tp" and tp["r_gross"] == pytest.approx(2.0)
    sl = _first(_bars([(100, 100, 100), (106, 99, 104), (101, 95, 96), (101, 95, 96), (101, 95, 96), (101, 95, 96)]), side=-1)
    assert sl["exit"] == "sl" and sl["r_gross"] == pytest.approx(-1.0)


def test_unresolved_tail_is_dropped_and_times_are_ordered():
    bars = _bars([(101, 99, 100)] * 6)
    out = labels.triple_barrier(bars, _sigma(bars), horizon=3, cost=FREE)
    assert len(out) == 3                       # events 0..2 resolve by bar 5; events 3, 4 do not
    assert (out["t1"] > out["t0"]).all() and out["t0"].is_monotonic_increasing


def test_bad_side_is_rejected():
    bars = _bars([(101, 99, 100)] * 6)
    with pytest.raises(ValueError):
        labels.triple_barrier(bars, _sigma(bars), side=0)


# ---------------------------------------------------------------- backtest


def _close(returns):
    return pd.Series(100 * np.cumprod(1 + np.asarray(returns)), index=pd.date_range("2024-01-01", periods=len(returns), freq="D", tz="UTC"))


def test_always_invested_pays_cost_only_once():
    close = _close([0.0] + [0.01] * 9)
    res = backtest.run(close, pd.Series(1.0, index=close.index), C)
    assert res["cost"].sum() == pytest.approx(C.one_way())      # one entry, no more trades
    assert res["gross"].iloc[1:].sum() == pytest.approx(0.01 * 9, rel=0.05)
    assert res["net"].sum() == pytest.approx(res["gross"].sum() - C.one_way())


def test_positions_apply_to_the_next_days_return_not_the_same_day():
    close = _close([0.0, 0.10, -0.10, 0.0])
    target = pd.Series([0.0, 1.0, 0.0, 0.0], index=close.index)   # decided at close of day 1, after the +10%
    res = backtest.run(close, target, FREE)
    assert res["gross"].iloc[1] == 0.0                              # the +10% day is NOT earned
    assert res["gross"].iloc[2] == pytest.approx(-0.10)             # the -10% day is


def test_no_trade_band_suppresses_small_rebalances():
    close = _close([0.0] * 8)
    target = pd.Series([0.5, 0.55, 0.5, 0.52, 0.48, 0.5, 0.53, 0.5], index=close.index)
    res = backtest.run(close, target, C, band=0.10)
    assert res["turnover"].sum() == pytest.approx(0.5)             # only the first entry traded


def test_exit_to_flat_ignores_the_band():
    close = _close([0.0] * 5)
    target = pd.Series([0.5, 0.45, 0.0, 0.0, 0.0], index=close.index)
    res = backtest.run(close, target, FREE, band=0.20)
    assert res["position"].iloc[3] == 0.0                          # got out even though 0.45 -> 0 is a small change


# ---------------------------------------------------------------- causality


def _walk(n=900, seed=0):
    rng = np.random.default_rng(seed)
    return _close(rng.normal(0.0005, 0.03, n))


@pytest.mark.parametrize("k", [300, 520, 700])
def test_baseline_positions_do_not_change_when_future_data_is_added(k):
    close = _walk()

    def pos(c):
        return baselines.vol_scaled(baselines.trend_signal(c), baselines.ewma_vol(c))

    full, prefix = pos(close).iloc[:k], pos(close.iloc[:k])
    pd.testing.assert_series_equal(full, prefix, check_names=False)


def test_vol_scaled_position_is_long_only_and_never_leveraged():
    close = _walk()
    p = baselines.vol_scaled(baselines.trend_signal(close), baselines.ewma_vol(close), target_vol=0.5, max_leverage=1.0)
    assert p.min() >= 0.0 and p.max() <= 1.0


def test_trend_signal_is_flat_until_a_pair_has_enough_history():
    sig = baselines.trend_signal(_walk())
    assert (sig.iloc[:63] == 0).all()          # the first pair needs 64 days
    assert sig.iloc[:255].max() <= 2 / 3       # the slowest pair (256 days) cannot vote yet
