import json

import httpx
import numpy as np
import pandas as pd
import pytest

from getrich.news import gdelt_timeline as g


def answer(values, start="2020-01-01", skip=()):
    days = pd.date_range(start, periods=len(values), freq="D")
    data = [{"date": d.strftime("%Y%m%dT000000Z"), "value": v} for i, (d, v) in enumerate(zip(days, values)) if i not in skip]
    return {"query_details": {"date_resolution": "day"}, "timeline": [{"series": "x", "data": data}]}


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_timeline_reads_days_and_rejects_empty_answers():
    assert g.parse_timeline(answer([1.5, 2.5]))[0] == ("2020-01-01", 1.5)
    with pytest.raises(ValueError):
        g.parse_timeline({"timeline": []})


def test_fetch_all_asks_for_every_series_and_mode_once_caches_and_paces():
    calls, sleeps = [], []

    def handler(req):
        calls.append(dict(req.url.params))
        return httpx.Response(200, json=answer(list(np.linspace(0.01, 0.1, 30))))

    res = g.fetch_all(client=client_for(handler), pause_s=25, sleep=sleeps.append, end="20200130000000")
    assert res == {"fetched": 16, "cached": 0} and len(calls) == 16
    assert {c["mode"] for c in calls} == {"timelinevol", "timelinetone"} and all("sourcelang:english" in c["query"] for c in calls)
    assert all(c["startdatetime"] == "20200101000000" and c["enddatetime"] == "20200130000000" for c in calls)
    assert sleeps == [25] * 15                                         # patient: a pause between requests, none before the first
    again = g.fetch_all(client=client_for(handler), sleep=sleeps.append, end="20200130000000")
    assert again == {"fetched": 0, "cached": 16} and len(calls) == 16   # the cache makes a rerun free


def test_a_rate_limit_backs_off_and_retries_then_succeeds_or_gives_up():
    state, sleeps = {"n": 0}, []

    def flaky(req):
        state["n"] += 1
        return httpx.Response(429, text="Please limit requests") if state["n"] <= 2 else httpx.Response(200, json=answer([0.1] * 5))

    data = g.fetch_one(client_for(flaky), "btc", "vol", "20200105000000", sleep=sleeps.append)
    assert len(data) == 5 and sleeps == [90, 135]
    with pytest.raises(RuntimeError, match="http 429"):
        g.fetch_one(client_for(lambda r: httpx.Response(429, text="no")), "btc", "vol", "20200105000000", retries=1, sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="no timeline"):
        g.fetch_one(client_for(lambda r: httpx.Response(200, text="Query too short")), "btc", "vol", "20200105000000", sleep=lambda s: None)


def fill_cache(n=200, skip=(), vol_fn=None):
    rng = np.random.default_rng(0)
    for name in g.SERIES:
        for mode in g.MODES:
            v = list(0.05 + 0.01 * rng.standard_normal(n)) if mode == "vol" else list(-2 + 0.5 * rng.standard_normal(n))
            g.cache_dir().mkdir(parents=True, exist_ok=True)
            g.cache_path(name, mode).write_text(json.dumps({"data": g.parse_timeline(answer(v, skip=skip))}))


def test_load_daily_fills_gaps_forward_only_and_reports_them():
    fill_cache(60, skip=(20, 21, 22))
    frame, info = g.load_daily()
    assert info["days"] == 60 and info["days_missing_all_series"] == 3 and info["still_missing_after_fill"] == 0
    assert frame.index.tz is not None and frame.iloc[20].equals(frame.iloc[19])                 # the missing day carries yesterday's value, never tomorrow's


def test_a_long_gap_is_not_papered_over():
    fill_cache(60, skip=tuple(range(10, 30)))                                                     # twenty days missing
    frame, info = g.load_daily()
    assert info["still_missing_after_fill"] == 20 - g.MAX_FFILL_DAYS


def test_features_are_causal_scaled_and_neutral_without_history():
    fill_cache(250)
    frame, _ = g.load_daily()
    f = g.news_features(frame)
    assert list(f.columns) == g.FEATURES and len(g.FEATURES) == 16
    assert (f.iloc[:25] == 0).all().all()                                                          # not enough history yet: neutral, not invented
    assert f.abs().max().max() <= 5
    shifted = frame.copy()
    shifted.iloc[200:] = shifted.iloc[200:] * 5 + 3                                                # rewrite the future
    f2 = g.news_features(shifted)
    pd.testing.assert_frame_equal(f.iloc[:200], f2.iloc[:200])                                    # earlier features did not change


def test_a_load_without_a_fetch_says_what_to_run():
    with pytest.raises(RuntimeError, match="news-fetch"):
        g.load_daily()
