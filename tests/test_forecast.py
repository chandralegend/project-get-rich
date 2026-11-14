import numpy as np
import pandas as pd
import pytest

from getrich.forecast import base, evaluate as ev
from getrich.forecast.base import HORIZONS, QUANTILES, Cache, load_cache, validate_cube
from getrich.forecast.fakes import Momentum, Oracle, RandomWalk, Z
from getrich.forecast.features import foundation_features, prob_up
from getrich.forecast.generate import generate, index_ns


def make_bars(n=1400, seed=0, drift=0.0, vol=0.02, start="2020-01-01"):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    o = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, close) * 1.005, "low": np.minimum(o, close) * 0.995, "close": close, "volume": 10.0}, index=idx)


def oracle_for(bars):
    days = (index_ns(bars.index) // 86_400_000_000_000).tolist()
    return Oracle({d: c for d, c in zip(days, bars["close"])}, days)


def run_eval(fc, bars, release="2020-01-01", stride=3):
    generate(fc, "BTCUSDT", bars, stride=stride)
    return ev.evaluate_model({"BTCUSDT": load_cache(fc.name, "BTCUSDT")}, {"BTCUSDT": bars}, pd.Timestamp(release, tz="UTC"))


def row(res, window="all", h=5):
    return res[(res.window == window) & (res.h == h)].iloc[0]


# ------------------------------------------------------------------ generation is causal, incremental and validated


def test_a_forecast_at_an_origin_does_not_change_when_later_bars_change():
    a, b = make_bars(seed=1), make_bars(seed=1)
    cut = 700
    b.iloc[cut + 1:, b.columns.get_loc("close")] *= 3.0                       # rewrite the future after the cut
    b.iloc[cut + 1:, b.columns.get_loc("high")] *= 3.0
    b.iloc[cut + 1:, b.columns.get_loc("low")] *= 3.0
    fc = RandomWalk()
    generate(fc, "A", a, stride=1, max_new=None)
    ca = load_cache(fc.name, "A")
    (base.cache_path(fc.name, "A")).rename(base.cache_path(fc.name, "A_old"))
    generate(fc, "B", b, stride=1)
    cb = load_cache(fc.name, "B")
    shared = np.isin(ca.origins, cb.origins) & (ca.origins <= a.index[cut].to_datetime64().astype("datetime64[ns]"))
    assert shared.sum() > 500
    np.testing.assert_allclose(ca.cube[shared], cb.cube[np.isin(cb.origins, ca.origins[shared])])


def test_the_window_handed_to_the_forecaster_ends_at_the_origin():
    seen = []

    class Spy(RandomWalk):
        name = "spy"

        def forecast(self, ohlcv, ts):
            seen.append((ohlcv[:, -1, 3].copy(), ts[:, -1].copy(), ohlcv.shape))
            return super().forecast(ohlcv, ts)

    bars = make_bars(300)
    generate(Spy(), "A", bars, stride=7, batch=5)
    c = load_cache("spy", "A")
    last_closes = np.concatenate([s[0] for s in seen])
    expected = bars["close"].to_numpy()[np.isin(index_ns(bars.index), c.origins.astype("datetime64[ns]").astype("int64"))]
    np.testing.assert_allclose(last_closes, expected)                        # the newest bar in each window is the origin's own close
    assert all(s[2][1] == 64 for s in seen)


def test_generation_is_incremental_and_never_recomputes_or_duplicates():
    bars = make_bars(400)
    fc = RandomWalk()
    generate(fc, "A", bars, stride=2, max_new=30)
    first = load_cache(fc.name, "A")
    assert len(first) == 30
    generate(fc, "A", bars, stride=2)
    full = load_cache(fc.name, "A")
    assert len(full) == len(np.unique(full.origins)) > 100
    np.testing.assert_allclose(full.cube[np.isin(full.origins, first.origins)], first.cube[np.argsort(first.origins)])
    n = len(full)
    generate(fc, "A", bars, stride=2)
    assert len(load_cache(fc.name, "A")) == n


def test_the_cache_refuses_a_file_written_for_different_horizons(monkeypatch):
    bars = make_bars(200)
    generate(RandomWalk(), "A", bars, stride=5)
    monkeypatch.setattr(base, "HORIZONS", (1, 2, 3))
    with pytest.raises(RuntimeError, match="regenerate"):
        load_cache("fake_rw", "A")


def test_forecaster_output_is_validated():
    ok = np.zeros((2, len(HORIZONS), len(QUANTILES)))
    assert validate_cube(ok, 2)[1] == 0
    with pytest.raises(ValueError, match="shape"):
        validate_cube(ok, 3)
    bad = ok.copy()
    bad[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        validate_cube(bad, 2)
    crossed = ok.copy()
    crossed[0, 0] = [0.3, 0.1, 0.0, -0.1, -0.3]                               # descending quantiles
    fixed, n = validate_cube(crossed, 2)
    assert n == 1 and (np.diff(fixed, axis=-1) >= 0).all()


# ------------------------------------------------------------------ the evaluation can tell skill from none


def test_an_oracle_shows_large_skill_and_a_random_walk_shows_none():
    bars = make_bars(1400, seed=2)
    oracle = run_eval(oracle_for(bars), bars)
    rw = run_eval(RandomWalk(), bars)
    for h in (5, 20):
        o, r = row(oracle, h=h), row(rw, h=h)
        assert o.skill > 0.5 and o.ic > 0.9 and o.ic_lo > 0.8 and o.dm_p < 0.001
        assert abs(r.skill) < 0.03 and r.ic == 0.0 and r.location_skill == pytest.approx(0.0, abs=0.03)


def test_a_momentum_forecaster_on_pure_noise_is_not_credited_with_skill():
    bars = make_bars(1400, seed=3)
    res = run_eval(Momentum(), bars)
    for h in (5, 20):
        r = row(res, h=h)
        assert r.location_skill < 0.01 and not (r.skill > 0 and r.dm_p < 0.05)
        assert r.ic_lo < 0 < r.ic_hi


def test_momentum_is_credited_when_the_data_really_trend():
    rng = np.random.default_rng(4)
    n, mu, r = 1800, 0.0, []
    for _ in range(n):                                                        # a drift that persists for weeks, so trailing returns carry real information
        mu = 0.97 * mu + rng.normal(0, 0.0018)
        r.append(mu + rng.normal(0, 0.012))
    close = 100 * np.exp(np.cumsum(r))
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    o = np.concatenate([[close[0]], close[:-1]])
    bars = pd.DataFrame({"open": o, "high": close * 1.004, "low": close * 0.996, "close": close, "volume": 1.0}, index=idx)
    res = run_eval(Momentum(), bars)
    assert row(res, h=5).ic_lo > 0 and row(res, h=5).location_skill > 0


def test_coverage_exposes_an_overconfident_model():
    class Overconfident(RandomWalk):
        name = "fake_overconfident"

        def forecast(self, ohlcv, ts):
            return 0.4 * super().forecast(ohlcv, ts)

    bars = make_bars(1400, seed=5)
    good, bad = row(run_eval(RandomWalk(), bars), h=5), row(run_eval(Overconfident(), bars), h=5)
    assert abs(good.cov80 - 0.8) < 0.07 and abs(good.cov40 - 0.4) < 0.07
    assert bad.cov80 < 0.5 and bad.skill < good.skill - 0.1


def test_the_post_release_window_only_uses_origins_after_the_release_date():
    bars = make_bars(1400, seed=6)
    res = run_eval(RandomWalk(), bars, release="2023-06-01")
    allr, post = row(res, "all"), row(res, "post_release")
    assert post.n < allr.n and post["from"] >= pd.Timestamp("2023-06-01", tz="UTC")
    assert verdict_of(res) == "no skill versus a random walk after release"


def verdict_of(res):
    return ev.verdict(res)


def test_the_verdict_credits_an_oracle_and_never_a_random_walk():
    bars = make_bars(1400, seed=7)
    assert "shows skill" in ev.verdict(run_eval(oracle_for(bars), bars, release="2021-01-01"))
    assert ev.verdict(run_eval(RandomWalk(), bars, release="2021-01-01")).startswith("no skill")


def test_a_short_post_release_window_is_reported_as_unjudgeable():
    bars = make_bars(400, seed=8)
    res = run_eval(RandomWalk(), bars, release="2100-01-01")
    assert ev.verdict(res) == "not enough post-release data to judge"


# ------------------------------------------------------------------ features


def test_prob_up_and_features_are_scaled_by_volatility():
    sym = np.array([[-2.0, -0.6, 0.0, 0.6, 2.0]])
    assert prob_up(sym)[0] == pytest.approx(0.5)
    assert prob_up(sym + 5)[0] == pytest.approx(0.9) and prob_up(sym - 5)[0] == pytest.approx(0.1)      # clipped to the range the quantiles cover
    origins = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    cube = np.zeros((3, len(HORIZONS), len(QUANTILES)), dtype=np.float32)
    cube[:] = 0.05 * (np.arange(5) - 2)                                       # symmetric around zero, width 0.2
    cube[:, :, :] += 0.02                                                     # shifted up by 2%
    cache = Cache("m", "S", origins.tz_localize(None).to_numpy(dtype="datetime64[ns]"), cube)
    sigma = pd.Series(0.02, index=origins)
    f = foundation_features(cache, sigma, "m")
    assert f["m_med_h1"].iloc[0] == pytest.approx(0.02 / 0.02)
    assert f["m_med_h5"].iloc[0] == pytest.approx(0.02 / (0.02 * np.sqrt(5)))
    assert (f["m_pup_h5"] > 0).all() and f["m_skew_h5"].abs().max() < 1e-6
    assert f["m_width_h20"].iloc[0] == pytest.approx(0.2 / (0.02 * np.sqrt(20)))
    assert "m_width_h1" not in f.columns
