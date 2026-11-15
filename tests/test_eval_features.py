import numpy as np
import pandas as pd
import pytest

from getrich.eval import features
from getrich.eval.costs import CostModel


def _synthetic(days=1300, seed=0):
    rng = np.random.default_rng(seed)
    hidx = pd.date_range("2020-01-01", periods=days * 24, freq="h", tz="UTC")
    lr = rng.normal(0.00002, 0.004, len(hidx))
    close_h = 100 * np.exp(np.cumsum(lr))
    hourly = pd.DataFrame({"close": close_h}, index=hidx)
    g = hourly["close"].groupby(hidx.floor("D"))
    daily = pd.DataFrame({"open": g.first(), "high": g.max() * 1.002, "low": g.min() * 0.998, "close": g.last(),
                          "volume": rng.lognormal(10, 0.4, days)})
    return daily, hourly


@pytest.fixture(scope="module")
def frame():
    daily, hourly = _synthetic()
    return daily, hourly, features.build_symbol_frame("BTCUSDT", daily, hourly, CostModel())


def test_market_features_do_not_change_when_future_bars_are_added():
    daily, _ = _synthetic()
    full = features.market_features(daily)
    for k in (400, 700, 1000):
        prefix = features.market_features(daily.iloc[:k])
        pd.testing.assert_frame_equal(full.iloc[:k], prefix, check_freq=False)


def test_the_dataset_has_no_missing_values_and_labels_resolve_after_the_decision(frame):
    _, _, df = frame
    assert len(df) > 500
    assert not df[features.ALL].isna().any().any()
    assert (df["t1"] > df["t0"]).all()
    assert set(df["label"].unique()) <= {0, 1}


def test_a_decision_only_uses_features_from_its_own_bar(frame):
    daily, _, df = frame
    mf = features.market_features(daily)
    row = df.iloc[10]
    bar = df.index[10]
    assert row["ret_5"] == pytest.approx(mf.loc[bar, "ret_5"])
    assert row["t0"] == bar + pd.Timedelta(days=1)       # decided at that bar's close


def test_cost_repricing_matches_the_label_definition(frame):
    _, _, df = frame
    ds = features.from_frames([df])
    np.testing.assert_allclose(ds.r_at(1.0), ds.r_net, atol=1e-9)
    assert (ds.r_at(2.0) < ds.r_net).all()                # double the cost is strictly worse
    assert (ds.y == (ds.r_net > 0)).all()


def test_pooled_dataset_is_sorted_by_decision_time_and_keeps_both_assets():
    daily, hourly = _synthetic(seed=1)
    a = features.build_symbol_frame("BTCUSDT", daily, hourly, CostModel())
    b = features.build_symbol_frame("ETHUSDT", daily, hourly, CostModel())
    ds = features.from_frames([a, b])
    assert (np.diff(ds.t0.astype("int64")) >= 0).all()
    assert set(ds.asset) == {"BTCUSDT", "ETHUSDT"}
    assert ds.X.shape == (len(ds), len(features.ALL))
    assert ds.X[:, ds.columns.index("is_eth")].tolist() == [1.0 if s == "ETHUSDT" else 0.0 for s in ds.asset]


def test_channel_indices_cover_every_column_once():
    ds = features.from_frames([features.build_symbol_frame("BTCUSDT", *_synthetic(), CostModel())])
    idx = sorted(i for name in ds.channels for i in ds.channel_idx(name))
    assert idx == list(range(len(features.ALL)))


def test_foundation_features_become_an_extra_channel_and_restrict_rows_to_where_they_exist():
    from getrich.forecast.base import Cache
    from getrich.forecast.fakes import RandomWalk
    from getrich.forecast.features import foundation_features
    from getrich.forecast.generate import generate
    from getrich.eval import labels

    daily, hourly = _synthetic(900)
    base = features.build_symbol_frame("BTCUSDT", daily, hourly, CostModel())
    cache = generate(RandomWalk(), "BTCUSDT", daily, stride=1, since=daily.index[600])
    fnd = foundation_features(cache, labels.daily_vol(daily["close"]), "fake_rw")
    with_f = features.build_symbol_frame("BTCUSDT", daily, hourly, CostModel(), foundation=fnd)
    assert 0 < len(with_f) < len(base) and with_f.index.min() >= daily.index[600]
    assert not with_f[features.ALL + list(fnd.columns)].isna().any().any()
    ds = features.from_frames([with_f], extra=list(fnd.columns))
    assert ds.channels["foundation"] == list(fnd.columns) and ds.X.shape[1] == len(features.ALL) + len(fnd.columns)
    assert ds.channel_idx("foundation") == list(range(len(features.ALL), ds.X.shape[1]))
    plain = features.from_frames([base])
    assert "foundation" not in plain.channels and plain.X.shape[1] == len(features.ALL)           # existing runs are unchanged


def test_a_dataset_never_silently_drops_a_foundation_model_with_no_forecasts():
    daily, _ = _synthetic(300)
    with pytest.raises(RuntimeError, match="forecast-run"):
        features.foundation_frame("BTCUSDT", daily, ["chronos2"])


def _news_for(daily, start_offset=0, seed=1):
    from getrich.news import gdelt_timeline as g

    rng = np.random.default_rng(seed)
    idx = daily.index[start_offset:]
    return pd.DataFrame(rng.normal(0, 1, (len(idx), len(g.FEATURES))), index=idx, columns=g.FEATURES)


def test_a_news_channel_is_joined_by_day_and_restricts_rows_to_days_with_news():
    daily, hourly = _synthetic(900)
    base = features.build_symbol_frame("BTCUSDT", daily, hourly, CostModel())
    news = _news_for(daily, start_offset=500)
    joined = features.build_symbol_frame("BTCUSDT", daily, hourly, CostModel(), news=news)
    assert 0 < len(joined) < len(base) and joined.index.min() >= daily.index[500]
    assert set(news.columns) <= set(joined.columns) and not joined[list(news.columns)].isna().any().any()
    row = joined.index[10]
    assert joined.loc[row, news.columns[0]] == news.loc[row, news.columns[0]]                 # the value joined is the same day's, not a neighbour's


def test_channels_can_be_selected_without_changing_rows_labels_or_order():
    from getrich.forecast.fakes import RandomWalk
    from getrich.forecast.features import foundation_features
    from getrich.forecast.generate import generate

    daily, hourly = _synthetic(900)
    cache = generate(RandomWalk(), "BTCUSDT", daily, stride=1, since=daily.index[400])
    fnd = foundation_features(cache, labels_vol(daily), "fake_rw")
    news = _news_for(daily, start_offset=450)
    frame = features.build_symbol_frame("BTCUSDT", daily, hourly, CostModel(), foundation=fnd, news=news)
    ds = features.from_frames([frame], extra=list(fnd.columns), news_cols=list(news.columns))
    assert list(ds.channels) == ["market", "forecast", "context", "foundation", "news"]
    for names in (["market", "forecast", "context"], ["market", "forecast", "context", "foundation"], ["market", "forecast", "context", "news"], list(ds.channels)):
        sub = ds.subset(names)
        assert len(sub) == len(ds) and (sub.y == ds.y).all() and (sub.t0 == ds.t0).all() and (sub.r_net == ds.r_net).all()
        assert sub.X.shape[1] == sum(len(ds.channels[n]) for n in names) == len(sub.columns)
        for n in names:                                                                       # channel indices still point at the right columns
            np.testing.assert_array_equal(sub.X[:, sub.channel_idx(n)], ds.X[:, ds.channel_idx(n)])
    with pytest.raises(ValueError, match="unknown channels"):
        ds.subset(["market", "text"])


def labels_vol(daily):
    from getrich.eval import labels

    return labels.daily_vol(daily["close"])


def test_the_dataset_refuses_an_unknown_news_source():
    with pytest.raises(ValueError, match="only 'gdelt'"):
        features.news_frame("twitter")
