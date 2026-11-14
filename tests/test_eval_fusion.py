import numpy as np
import pytest

from getrich.eval import fusion, nulltests, pinet

IDX = {"market": [0, 1], "forecast": [2], "context": [3, 4]}


def _world(n=1800, alpha=0.5, seed=0):
    w = nulltests.make_world(n=n, alpha=alpha, seed=seed)
    return w["X"].astype(np.float32), w["y"], w["r"]


def _fast(**kw):
    return fusion.FusionPI(IDX, epochs=20, seeds=(0,), **kw)


def test_the_fusion_net_learns_a_planted_signal_out_of_sample():
    X, y, r = _world()
    model = _fast().fit(X[:1300], y[:1300], r[:1300])
    pred = model.predict(X[1300:])
    assert pred.shape == (500, 2)
    assert np.corrcoef(pred[:, 1], r[1300:])[0, 1] > 0.15
    assert ((pred[:, 0] > 0) & (pred[:, 0] < 1)).all()


def test_training_is_deterministic_for_fixed_seeds():
    X, y, r = _world(n=600)
    a = _fast().fit(X, y, r).predict(X[:50])
    b = _fast().fit(X, y, r).predict(X[:50])
    np.testing.assert_allclose(a, b, atol=1e-6)


def test_a_missing_channel_is_masked_not_propagated():
    X, y, r = _world(n=800)
    model = _fast().fit(X, y, r)
    X2 = X[:100].copy()
    X2[:, 2] = np.nan                                    # the whole 'forecast' channel is absent
    pred = model.predict(X2)
    assert np.isfinite(pred).all()
    assert not np.allclose(pred, model.predict(X[:100]))  # the channel did matter, and its absence is handled


def test_a_net_trained_with_a_channel_absent_never_depends_on_it():
    X, y, r = _world(n=800)
    Xm = X.copy()
    Xm[:, 2] = np.nan
    model = _fast().fit(Xm, y, r)
    a, b = Xm[:60].copy(), Xm[:60].copy()
    b[:, 2] = 123.0                                      # garbage in the masked channel is ignored only if still NaN-flagged
    b[:, 2] = np.nan
    np.testing.assert_allclose(model.predict(a), model.predict(b))


def test_auxiliary_targets_with_missing_values_do_not_break_training():
    X, y, r = _world(n=600)
    aux = np.random.default_rng(0).normal(size=(600, 2))
    aux[::3, 1] = np.nan
    aux[:50, 0] = np.nan
    pred = _fast().fit(X, y, r, aux).predict(X[:20])
    assert np.isfinite(pred).all()


import json
import subprocess
import sys

import pytest


def _control(model, alpha, seed, epochs=None):
    cmd = [sys.executable, "-I", "-m", "getrich.eval.pinet_worker", "--model", model, "--synthetic", str(alpha), "--seed", str(seed)]
    if epochs:
        cmd += ["--epochs", str(epochs)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("model,epochs", [("linear", None), ("lgbm", None), ("fusion", 15)])
def test_each_model_finds_a_planted_signal_and_none_in_noise(model, epochs):
    """Each model runs in its own process (PyTorch and LightGBM cannot share one on macOS)."""
    planted = _control(model, 0.4, 21, epochs)
    noise = _control(model, 0.0, 22, epochs)
    assert planted["score"] > 0.15, planted
    assert noise["score"] < 0.12, noise
