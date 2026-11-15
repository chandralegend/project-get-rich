import numpy as np
import pandas as pd
import pytest

from getrich.eval import portfolio_study as ps
from getrich.eval.costs import CostModel


def world(n=700, k=6, seed=0, drift=0.0006):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    r = rng.normal(drift, 0.03, (n, k))
    close = pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=idx, columns=[f"C{i}" for i in range(k)])
    close.iloc[:50, 2:] = np.nan                     # coins that start later
    close.iloc[600:, 1] = np.nan                     # a coin that disappears
    return close


def test_weights_never_leverage_and_respect_eligibility():
    close = world()
    w = ps.weights(close)
    elig = ps.eligible(close)
    for k, frame in w.items():
        assert (frame.sum(axis=1) <= 1 + 1e-9).all(), k
        assert (frame >= -1e-12).all().all()
        assert (frame.where(~elig, 0.0) == 0.0).all().all() or k in ()   # no weight on a coin that is not eligible
        assert (frame[~elig].fillna(0.0).abs().sum().sum()) < 1e-9, k


def test_momentum_holds_at_most_top_k_and_only_uptrends():
    close = world(seed=3)
    w = ps.weights(close)["S4"]
    assert ((w > 0).sum(axis=1) <= ps.TOP_K).all()
    sig = ps.signals(close)
    assert ((w > 0) <= (sig >= 2 / 3 - 1e-9)).all().all()


def test_weights_are_causal_changing_the_future_does_not_change_the_past():
    close = world(seed=5)
    cut = 500
    base = ps.weights(close)
    altered = close.copy()
    altered.iloc[cut + 1:] = altered.iloc[cut + 1:] * 3.7
    other = ps.weights(altered)
    for k in base:
        pd.testing.assert_frame_equal(base[k].iloc[: cut + 1], other[k].iloc[: cut + 1], check_exact=False, atol=1e-9)


def test_volatility_target_only_scales_down():
    close = world(seed=7)
    w = ps.weights(close)
    assert (w["S3"].sum(axis=1) <= w["S1"].sum(axis=1) + 1e-9).all()


def test_costs_reduce_returns_and_stress_reduces_more():
    close = world(seed=9)
    w = ps.weights(close)["S4"]
    a = ps.portfolio_returns(close, w, CostModel())
    b = ps.portfolio_returns(close, w, CostModel().stressed(2.0))
    assert a["cost"].sum() > 0 and b["cost"].sum() > a["cost"].sum()
    assert abs((a["gross"] - a["cost"] - a["net"]).abs().max()) < 1e-12


def test_bootstrap_difference_sees_a_planted_gap_and_not_noise():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 0.01, 1500)
    better = noise + 0.003
    gap = ps.block_bootstrap_diff(better, noise, reps=200)
    same = ps.block_bootstrap_diff(noise, noise * 1.0, reps=200)
    assert gap["lo"] > 0 and gap["p_better"] > 0.95
    assert same["lo"] <= 0 <= same["hi"]


def test_run_refuses_an_unlogged_preregistration(monkeypatch):
    monkeypatch.setattr(ps, "prereg_events", lambda: [])
    with pytest.raises(RuntimeError, match="does not match any logged hash"):
        ps.run(close=world(), register=False)


def test_run_end_to_end_on_synthetic_data_without_registering():
    res = ps.run(close=world(n=1500, k=8, seed=2).rename(columns={"C0": "BTCUSDT"}), register=False, require_prereg=False)
    assert set(res["rows"]) == set(ps.STRATEGIES)
    s1 = res["rows"]["S1"]
    assert set(s1["criteria"]) == {"gain_vs_both", "dsr", "both_halves_positive", "drawdown"}
    assert "S1" in ps.to_markdown(res)
