import numpy as np

from getrich.trading import limits as L
from getrich.trading import replay_voltarget as rv
from getrich.trading.replay import ReplayConfig

from test_replay import two

LIM = L.Limits("moderate", 0.5, 0.30, 0.055, "x", 0.02)


def test_invariants_hold_and_the_cash_never_goes_negative_over_random_histories():
    for seed in range(6):
        for drift in (0.003, 0.0, -0.002):
            res, info = rv.run(two(seed, drift=drift, vol=0.03), ReplayConfig(limits=LIM))
            assert res.violations == [], (seed, drift, res.violations[:2])
            assert (res.equity > 0).all()
            assert (res.exposure <= LIM.max_exposure_fraction + 0.15).all()      # marked exposure may drift above the cap after entry, never wildly


def test_positions_are_sized_by_the_volatility_target_and_never_added_to():
    res, info = rv.run(two(drift=0.004, vol=0.02), ReplayConfig(limits=LIM))
    assert info["events"].get("entry", 0) >= 2
    assert info["mean_requested_weight"] <= rv.SLEEVE + 1e-9                    # a sleeve is at most half of equity before the gate
    assert "add" not in info["events"]


def test_a_downtrend_stays_mostly_in_cash():
    res, _ = rv.run(two(drift=-0.004, vol=0.02), ReplayConfig(limits=LIM))
    assert res.exposure.mean() < 0.15


def test_a_tighter_exposure_cap_never_lets_exposure_exceed_it_at_entry():
    tight = L.Limits("t", 0.05, 0.30, 0.055, "x", 0.02)
    res, info = rv.run(two(drift=0.004, vol=0.02), ReplayConfig(limits=tight))
    assert res.violations == []
    assert info["binding"].get("exposure cap", 0) + info["binding"].get("risk budget", 0) + info["binding"].get("requested quantity", 0) == info["events"].get("entry", 0)


def test_entering_only_at_two_of_three_votes_takes_no_more_entries_and_the_default_is_unchanged():
    bars = two(seed=4, drift=0.002, vol=0.03)
    cfg = ReplayConfig(limits=LIM)
    base, bi = rv.run(bars, cfg)
    same, si = rv.run(bars, cfg, 0.0)
    strict, ti = rv.run(bars, cfg, 2 / 3)
    assert base.equity.equals(same.equity) and bi == si                          # the default is the original strategy
    assert ti["events"].get("entry", 0) <= bi["events"].get("entry", 0)
    assert strict.violations == []


def test_the_study_refuses_an_unlogged_preregistration(monkeypatch):
    import pytest

    import getrich.eval.channel_ablation as ca
    monkeypatch.setattr(ca, "prereg_events", lambda: [])
    with pytest.raises(RuntimeError, match="does not match any logged hash"):
        rv.study(limits=LIM, register=False, bars=two())
