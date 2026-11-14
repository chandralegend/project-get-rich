import numpy as np
import pandas as pd
import pytest

from getrich.eval import pinet_eval
from getrich.eval.costs import CostModel
from getrich.eval.features import Dataset

C = CostModel()


def _setup(n=300, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.02, n)), index=idx)
    bar = idx[:-10]                                         # the last 10 days have no resolved label
    m = len(bar)
    ds = Dataset(X=np.zeros((m, 1), dtype=np.float32), y=np.zeros(m, dtype=int), r_net=np.zeros(m), r_gross=np.zeros(m),
                 cost_r=np.full(m, 0.1), t0=(bar + pd.Timedelta(days=1)).to_numpy("datetime64[ns]"),
                 t1=(bar + pd.Timedelta(days=4)).to_numpy("datetime64[ns]"), asset=np.array(["A"] * m), bar=bar,
                 aux=np.full((m, 2), np.nan), columns=["x"], channels={"market": ["x"]})
    return ds, {"A": close}


def _pred(ds, e):
    out = np.zeros((len(ds), 2))
    out[:, 1] = e
    return out


def test_a_model_that_is_always_positive_matches_buy_and_hold():
    ds, closes = _setup()
    model = pinet_eval.model_returns(ds, _pred(ds, 1.0), closes, C)
    hold = pinet_eval.baseline_returns(ds, closes, C)["buy_and_hold"]
    pd.testing.assert_series_equal(model, hold, check_names=False)


def test_a_model_that_is_never_positive_stays_in_cash():
    ds, closes = _setup()
    r = pinet_eval.model_returns(ds, _pred(ds, -1.0), closes, C)
    assert (r == 0).all()


def test_a_model_is_judged_only_on_the_window_where_it_has_predictions():
    ds, closes = _setup()
    r = pinet_eval.model_returns(ds, _pred(ds, 1.0), closes, C)
    assert r.index.min() == ds.bar.min() and r.index.max() == ds.bar.max()


def test_higher_costs_never_improve_a_model_that_trades():
    ds, closes = _setup()
    e = np.where(np.arange(len(ds)) % 40 < 20, 1.0, -1.0)   # flips every 20 days
    base = pinet_eval.model_returns(ds, _pred(ds, e), closes, C).sum()
    hard = pinet_eval.model_returns(ds, _pred(ds, e), closes, C.stressed(2.0)).sum()
    assert hard < base


def test_summary_counts_every_model_and_baseline_as_a_trial():
    ds, closes = _setup()
    rng = np.random.default_rng(1)
    results = [pinet_eval.evaluate_model(f"m{i}", [_pred(ds, rng.normal(size=len(ds)))] * 2, ds, closes, C) for i in range(3)]
    base = pinet_eval.baseline_returns(ds, closes, C)
    out = pinet_eval.summarize(results, base, pinet_eval.baseline_returns(ds, closes, C.stressed(2.0)))
    assert out["n_trials"] == 3 + len(base) == 5
    assert all(m["n_trials"] == 5 for m in out["models"])
    assert all(np.isfinite(b["sharpe_2x"]) for b in out["baselines"])
