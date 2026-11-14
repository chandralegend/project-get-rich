import numpy as np
import pandas as pd
import pytest

from getrich.eval import limits


def test_ceil_to_rounds_up_to_the_step():
    assert limits.ceil_to(0.149, 0.05) == pytest.approx(0.15)
    assert limits.ceil_to(0.15, 0.05) == pytest.approx(0.15)   # no float surprise on an exact multiple
    assert limits.ceil_to(0.151, 0.05) == pytest.approx(0.20)
    assert limits.ceil_to(0.026, 0.005) == pytest.approx(0.030)


def test_max_drawdowns_on_known_paths():
    paths = np.array([[0.10, -0.20, 0.05], [0.01, 0.01, 0.01], [-0.5, 0.0, 0.0]])
    assert limits.max_drawdowns(paths) == pytest.approx([0.20, 0.0, 0.5])


def test_stationary_bootstrap_shape_and_block_structure():
    r = np.arange(1000, dtype=float)
    paths = limits.stationary_bootstrap(r, n_paths=200, horizon=400, mean_block=20, seed=1)
    assert paths.shape == (200, 400)
    steps = np.diff(paths, axis=1)
    consecutive = np.mean(steps == 1)                  # within a block the next sample follows the last
    assert 0.9 < consecutive < 1.0                      # about 1 - 1/20 of steps continue a block


def test_bootstrap_of_a_constant_series_has_the_constant_mean():
    paths = limits.stationary_bootstrap(np.full(500, 0.001), n_paths=50, horizon=100)
    assert np.allclose(paths, 0.001)


def test_worst_rolling_drop_finds_the_crash():
    idx = pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC")
    close = pd.Series(100.0, index=idx)
    close.iloc[100:] = 60.0                             # a 40% fall at hour 100
    drop, when = limits.worst_rolling_drop(close, 24)
    assert drop == pytest.approx(0.40) and when == idx[100]


def test_worst_events_are_separated():
    idx = pd.date_range("2024-01-01", periods=24 * 30, freq="h", tz="UTC")
    close = pd.Series(100.0, index=idx)
    close.iloc[200:] = 70.0
    close.iloc[500:] = 40.0
    events = limits.worst_events(close, 24, n=3, separation_days=3)
    stamps = [e[0] for e in events]
    assert all(abs((a - b).total_seconds()) > 3 * 86400 for i, a in enumerate(stamps) for b in stamps[:i])


def _derive(seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=1500, freq="D", tz="UTC")
    trend = pd.DataFrame({"A:trend": rng.normal(0.0008, 0.02, 1500), "B:trend": rng.normal(0.0008, 0.025, 1500)}, index=idx)
    hidx = pd.date_range("2021-01-01", periods=24 * 400, freq="h", tz="UTC")
    hourly = {"A": pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(hidx)))), index=hidx)}
    return limits.derive(trend, hourly, seed=seed)


def test_risk_scales_with_the_exposure_cap_and_halts_are_ordered():
    res = _derive()
    caps = sorted(res["profiles"].values(), key=lambda p: p["exposure_cap"])
    dd = [p["bootstrap_1y_max_drawdown"][95] for p in caps]
    events = [p["worst_24h_event_loss_x1_5"] for p in caps]
    assert dd == sorted(dd) and events == sorted(events)
    halts = [p["proposed_account_drawdown_halt"] for p in caps]
    assert halts == sorted(halts)


def test_recommendation_is_the_largest_profile_whose_gap_fits_inside_its_halt():
    res = _derive()
    coherent = [n for n, p in res["profiles"].items() if p["gap_fits_inside_halt"]]
    if coherent:
        best = max(coherent, key=lambda n: res["profiles"][n]["exposure_cap"])
        assert res["recommended"] == best
    for n, p in res["profiles"].items():
        assert p["gap_fits_inside_halt"] == (p["worst_24h_event_loss_x1_5"] <= p["proposed_account_drawdown_halt"] + 1e-9)


def test_toml_is_marked_as_a_proposal():
    res = _derive()
    text = limits.to_toml(res, res["recommended"])
    assert "PROPOSED" in text and "Not active" in text and "max_exposure_fraction" in text
