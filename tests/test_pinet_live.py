import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from getrich import config
from getrich.eval import features, labels, pinet_live as pl
from getrich.eval.costs import CostModel
from getrich.forecast.fakes import RandomWalk
from getrich.forecast.generate import generate
from getrich.obs.events import utcnow
from getrich.store.db import connect


def make_daily(n=700, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.025, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    o = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, close) * (1 + rng.uniform(0, 0.02, n)), "low": np.minimum(o, close) * (1 - rng.uniform(0, 0.02, n)),
                         "close": close, "volume": rng.uniform(50, 150, n)}, index=idx)


def make_hourly(daily, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(daily.index[0], periods=len(daily) * 24, freq="h", tz="UTC")
    px = np.repeat(daily["close"].to_numpy(), 24) * np.exp(rng.normal(0, 0.004, len(idx)))
    return pd.DataFrame({"open": px, "high": px * 1.002, "low": px * 0.998, "close": px, "volume": 10.0}, index=idx)


class Chronos(RandomWalk):
    name = "chronos2"


# ------------------------------------------------------------------ the frozen definition


def test_the_constants_are_the_researchs_and_the_preregistration_pins_the_model():
    from getrich.eval.pinet_worker import META_KWARGS

    assert (pl.TP_MULT, pl.SL_MULT, pl.HORIZON, pl.MIN_VOTES) == (META_KWARGS["tp_mult"], META_KWARGS["sl_mult"], META_KWARGS["horizon"], META_KWARGS["primary_min_votes"])
    doc = Path(__file__).parent.parent.joinpath(pl.PREREG).read_text()
    assert pl.PINNED_SHA256 in doc and str(pl.SEED) in doc and "180 days" in doc and "150 resolved" in doc


def test_a_model_file_that_is_not_the_pinned_one_is_refused(tmp_path, monkeypatch):
    p = pl.model_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"not the model")
    with pytest.raises(RuntimeError, match="does not match the hash pinned"):
        pl.load_model()


def test_nothing_is_recorded_until_the_preregistration_is_logged(monkeypatch):
    with pytest.raises(RuntimeError, match="pre-registration is not logged"):
        pl.predict_all(model=object(), meta={"columns": []})


# ------------------------------------------------------------------ the live resolver is the research labelling


def test_the_live_resolver_gives_the_same_outcome_as_the_research_triple_barrier_on_every_entry():
    daily = make_daily(500, seed=4)
    sigma = labels.daily_vol(daily["close"])
    lab = labels.triple_barrier(daily, sigma, tp_mult=pl.TP_MULT, sl_mult=pl.SL_MULT, horizon=pl.HORIZON, cost=CostModel())
    assert len(lab) > 200 and set(lab["exit"]) >= {"sl", "tp", "timeout"}
    pos = {t: i for i, t in enumerate(daily.index + pd.Timedelta(days=1))}
    for _, r in lab.iterrows():
        i = pos[r["t0"]]
        res = pl.resolve(float(daily["close"].iloc[i]), r["stop_frac"], r["tp_frac"], pl.HORIZON, daily.iloc[i + 1:])
        assert res["exit"] == {"sl": "sl", "tp": "tp", "timeout": "timeout"}[r["exit"]] and res["bars_held"] == r["bars_held"]
        assert res["r_net"] == pytest.approx(r["r_net"], abs=1e-9)


def test_an_entry_resolves_as_soon_as_a_barrier_is_touched_and_not_before():
    daily = make_daily(100, seed=2)
    entry, stop, tp = float(daily["close"].iloc[10]), 0.05, 0.20
    after = daily.iloc[11:]
    full = pl.resolve(entry, stop, tp, 20, after)
    assert full is not None
    k = full["bars_held"]
    assert pl.resolve(entry, stop, tp, 20, after.iloc[:k]) == full                      # the bars up to the exit are enough
    if k > 1:
        assert pl.resolve(entry, stop, tp, 20, after.iloc[:k - 1]) is None              # one fewer and it is still open


# ------------------------------------------------------------------ the live feature row equals the training row


def test_the_live_row_for_a_past_day_equals_the_training_row_built_with_later_data_present():
    daily, sym = make_daily(700), "BTCUSDT"
    hourly = make_hourly(daily)
    generate(Chronos(), sym, daily, stride=1)
    fnd = features.foundation_frame(sym, daily, ["chronos2"])
    train = features.build_symbol_frame(sym, daily, hourly, CostModel(), foundation=fnd, tp_mult=4.0, sl_mult=2.0, horizon=20, primary_min_votes=2 / 3)
    cols = list(features.ALL) + list(fnd.columns)
    assert len(train) > 100
    for bar in train.index[[10, len(train) // 2, -5]]:
        k = daily.index.get_loc(bar)
        d = pl.decision_row(sym, daily.iloc[:k + 1], hourly[hourly.index < bar + pd.Timedelta(days=1)], cols)
        assert d["status"] == "ready" and d["bar"] == bar
        assert np.allclose(d["row"].to_numpy(float), train.loc[bar, cols].to_numpy(float), rtol=1e-9, atol=1e-12), bar


def test_the_row_waits_for_the_days_hourly_bars_and_for_the_days_forecast():
    daily, sym = make_daily(500), "BTCUSDT"
    hourly = make_hourly(daily)
    cols = list(features.ALL)
    short = hourly[hourly.index < daily.index[-1] + pd.Timedelta(hours=10)]
    assert pl.decision_row(sym, daily, short, cols)["status"] == "waiting_for_hourly_bars"
    assert pl.decision_row(sym, daily, hourly, cols)["status"] == "no_forecast_cache"
    generate(Chronos(), sym, daily.iloc[:-1], stride=1)
    assert pl.decision_row(sym, daily, hourly, cols)["status"] == "waiting_for_the_forecast"


# ------------------------------------------------------------------ recording and scoring


class Stub:
    def __init__(self, e):
        self.e = e

    def predict(self, X):
        return np.array([[0.4, self.e]] * len(X))


def seed_daily_db(n=60, start_back=40):
    rng = np.random.default_rng(9)
    now = utcnow()
    first = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=start_back)
    with connect() as con:
        p = 100 * np.cumprod(1 + rng.normal(0.001, 0.02, n))
        con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [("binance", "BTCUSDT", "1d", first - timedelta(days=n - 1 - i), x, x * 1.01, x * 0.99, x, 100.0, 1.0, 1, now) for i, x in enumerate(p)])
        con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [("binance", "BTCUSDT", "1h", first - timedelta(days=n - 1 - i // 24) + timedelta(hours=i % 24), x, x * 1.001, x * 0.999, x, 10.0, 1.0, 1, now) for i, x in enumerate(np.repeat(p, 24))])


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(pl, "prereg_logged", lambda: True)
    monkeypatch.setattr(pl, "SYMBOLS", ("BTCUSDT",))

    def fake(votes=1.0):
        def f(sym, daily, hourly, cols):
            return {"status": "ready", "bar": daily.index[-1], "row": pd.Series({"trend_votes": votes, "a": 1.0}), "sigma": 0.02, "entry": float(daily["close"].iloc[-1]), "trend_votes": votes}
        return f
    return fake


def test_a_decision_is_recorded_once_with_its_inputs_and_the_call_follows_the_expected_r(monkeypatch, ready):
    seed_daily_db()
    monkeypatch.setattr(pl, "decision_row", ready(1.0))
    out = pl.predict_all(("BTCUSDT",), model=Stub(0.3), meta={"columns": ["trend_votes", "a"], "to": "2026-10-25"})
    assert out[0]["status"] == "recorded" and out[0]["call"] == "take"
    again = pl.predict_all(("BTCUSDT",), model=Stub(0.3), meta={"columns": ["trend_votes", "a"]})
    assert again[0]["status"] == "already_recorded"
    with connect() as con:
        n = con.execute("SELECT count(*) FROM insights WHERE json_extract_string(payload, '$.kind') = 'pinet_prediction'").fetchone()[0]
        ev = con.execute("SELECT count(*) FROM news_items WHERE source = 'pinet_inputs'").fetchone()[0]
    assert n == 1 and ev == 1
    assert pl.latest()["BTCUSDT"]["call"] == "take"


def test_negative_expected_r_is_a_skip_and_a_day_outside_the_trend_filter_is_never_scored(monkeypatch, ready):
    seed_daily_db()
    monkeypatch.setattr(pl, "decision_row", ready(1.0))
    assert pl.predict_all(("BTCUSDT",), model=Stub(-0.2), meta={"columns": ["trend_votes", "a"]})[0]["call"] == "skip"

    class Boom:
        def predict(self, X):
            raise AssertionError("the model must not score a day outside its domain")

    monkeypatch.setattr(pl, "_already", lambda con, s, b: False)               # record a second decision for the same bar, now outside the domain
    monkeypatch.setattr(pl, "decision_row", ready(1 / 3))
    assert pl.predict_all(("BTCUSDT",), model=Boom(), meta={"columns": ["trend_votes", "a"]})[0]["call"] == "out_of_domain"
    assert pl.score()["pending"] == 1                                         # only the in-domain skip is a study decision


def test_scoring_resolves_open_decisions_when_the_bars_arrive_and_is_idempotent(monkeypatch, ready):
    seed_daily_db(start_back=40)
    monkeypatch.setattr(pl, "decision_row", ready(1.0))
    pl.predict_all(("BTCUSDT",), model=Stub(0.3), meta={"columns": ["trend_votes", "a"]})
    assert pl.score() == {"resolved": 0, "pending": 1}                   # no bar after the decision bar yet
    # five more closed daily bars, one of which crashes through the stop
    last = pd.Timestamp(pl.latest()["BTCUSDT"]["decision_bar"], tz="UTC")
    with connect() as con:
        entry = float(con.execute("SELECT close FROM bars WHERE symbol = 'BTCUSDT' AND timeframe = '1d' ORDER BY ts_open DESC LIMIT 1").fetchone()[0])
        for i in range(1, 6):
            px = entry * (0.7 if i == 3 else 1.0)
            con.execute("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ["binance", "BTCUSDT", "1d", last + timedelta(days=i), entry, entry, px, px, 100.0, 1.0, 1, utcnow()])
    assert pl.score() == {"resolved": 1, "pending": 0}
    assert pl.score() == {"resolved": 0, "pending": 0}
    rec = pl.records()[0]
    assert rec["exit"] == "sl" and rec["r"] < -1 and rec["r2"] < rec["r"]


# ------------------------------------------------------------------ the pre-registered verdict


def recs(n_days=200, edge=0.0, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for d in range(n_days):
        for sym in ("BTCUSDT", "ETHUSDT"):
            call = "take" if rng.random() < 0.5 else "skip"
            r = rng.normal(0.0, 1.0) + (edge if call == "take" else -edge)
            out.append({"date": f"{(pd.Timestamp('2026-11-16') + pd.Timedelta(days=d)):%Y-%m-%d}", "symbol": sym, "call": call, "p": 0.4, "e": 0.1, "r": r, "r2": r - 0.05, "exit": "tp"})
    return out


def test_the_verdict_is_not_due_before_180_days_and_150_resolved_decisions():
    v = pl.verdict(recs(60), today="2026-12-20")
    assert not v["due"] and v["left"]["days"] > 0 and not v["shows_value"]


def test_a_real_edge_passes_and_pure_noise_does_not():
    good = pl.verdict(recs(400, edge=0.6), today="2028-01-01")
    assert good["due"] and good["p"] < 0.05 and good["summary"]["delta"] >= 0.10
    noise = pl.verdict(recs(400, edge=0.0, seed=3), today="2028-01-01")
    assert noise["due"] and not noise["shows_value"]


def test_the_block_bootstrap_is_reproducible_and_blocks_keep_both_coins_together():
    r = recs(300, edge=0.2)
    assert pl.block_p(r) == pl.block_p(r)
    assert pl.block_p([x for x in r if x["call"] == "skip"]) is None
