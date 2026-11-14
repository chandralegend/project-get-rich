import numpy as np
import pytest

from getrich.eval import nulltests, validate
from getrich.eval.splits import CombinatorialPurgedCV

DAY = np.timedelta64(1, "D")


def test_every_harness_control_passes():
    results = validate.run()
    failed = [c for c in results if not c.passed]
    assert not failed, "\n".join(f"{c.name}: {c.detail}" for c in failed)
    assert len(results) == 4


def test_ridge_logit_learns_a_simple_rule():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(1000, 3))
    y = (X[:, 0] + 0.1 * rng.normal(size=1000) > 0).astype(int)
    p = nulltests.RidgeLogit().fit(X, y).predict_proba(X)
    assert ((p > 0.5) == y).mean() > 0.95


def test_world_outcomes_overlap_like_real_labels():
    w = nulltests.make_world(n=3000, alpha=0.0, seed=1, horizon=10)
    r = w["r"]
    lag1 = np.corrcoef(r[:-1], r[1:])[0, 1]
    lag15 = np.corrcoef(r[:-15], r[15:])[0, 1]
    assert lag1 > 0.8                    # neighbouring outcomes share most of their shocks
    assert abs(lag15) < 0.1              # outcomes further apart than the horizon are independent


def test_shift_null_keeps_label_structure_but_breaks_the_link_to_features():
    w = nulltests.make_world(n=500, alpha=0.5, seed=3)
    rolled = np.roll(w["r"], 100)
    assert np.corrcoef(w["X"][:, 0], w["r"])[0, 1] > 0.3
    assert abs(np.corrcoef(w["X"][:, 0], rolled)[0, 1]) < 0.2
    assert np.isclose(np.corrcoef(w["r"][:-1], w["r"][1:])[0, 1], np.corrcoef(rolled[:-1], rolled[1:])[0, 1], atol=0.05)


def test_unknown_null_kind_is_rejected():
    w = nulltests.make_world(n=400)
    cv = CombinatorialPurgedCV(4, 2)
    with pytest.raises(ValueError):
        nulltests.null_pvalue(nulltests.RidgeLogit, w["X"], w["y"], w["r"], w["t0"], w["t1"], cv, kind="bogus", n_null=2)


def test_a_model_that_takes_too_few_trades_scores_zero_not_a_lucky_number():
    p = np.zeros(200)
    p[:5] = 1.0                           # takes only 5 trades, below MIN_TRADES
    r = np.random.default_rng(0).normal(size=200)
    assert nulltests._score(p, r, 0.5) == 0.0
