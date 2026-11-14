import numpy as np
import pandas as pd
import pytest

from getrich.eval import har


def _hourly(hours, step=0.001):
    idx = pd.date_range("2024-01-01", periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"close": 100 * np.exp(step * np.arange(hours))}, index=idx)


def test_realised_variance_is_the_sum_of_squared_hourly_returns():
    rv = har.daily_rv_from_hourly(_hourly(24 * 3 + 5))
    # day 1 has only 23 returns (no return for the first bar) and the last day is partial: both dropped
    assert len(rv) == 2
    assert rv.iloc[0] == pytest.approx(24 * 0.001**2)


def _synthetic_rv(n=1500, phi=0.92, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + rng.normal(0, 0.25)
    return pd.Series(np.exp(-9 + x), index=pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"))


def test_har_beats_yesterday_on_persistent_volatility():
    rv = _synthetic_rv()
    f = har.har_forecast(rv)
    realised_next = rv.shift(-1)
    naive = rv  # yesterday's value as the forecast
    har_loss = har.qlike(f.dropna(), realised_next)
    naive_loss = har.qlike(naive.loc[f.dropna().index], realised_next)
    assert har_loss < naive_loss


@pytest.mark.parametrize("k", [500, 800, 1100])
def test_har_forecasts_do_not_change_when_future_data_is_added(k):
    rv = _synthetic_rv()
    full = har.har_forecast(rv).iloc[:k]
    prefix = har.har_forecast(rv.iloc[:k])
    pd.testing.assert_series_equal(full, prefix, check_names=False)


def test_har_gives_no_forecast_before_enough_history():
    rv = _synthetic_rv(n=600)
    f = har.har_forecast(rv, min_train=365)
    assert f.iloc[:380].isna().all() and f.iloc[-1] > 0


def test_qlike_is_zero_for_a_perfect_forecast_and_penalises_errors():
    a = pd.Series([1.0, 2.0, 3.0])
    assert har.qlike(a, a) == pytest.approx(0.0)
    assert har.qlike(a * 2, a) > 0 and har.qlike(a / 2, a) > 0
