import json
import math
import py_compile
import sys

import numpy as np
import pytest

from getrich import cli
from getrich.forecast import fetch, models
from getrich.forecast.base import load_cache
from getrich.forecast.fakes import RandomWalk
from getrich.forecast.generate import generate
from getrich.forecast.runner import WORKERS, ModelSpec, SubprocessForecaster

from test_forecast import make_bars

WORKER = '''
import os, sys
import numpy as np
from scipy.stats import norm
assert os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "worker must run offline"
leaked = [k for k in os.environ if k.startswith(("ANTHROPIC", "GETRICH", "AWS", "GITHUB", "OPENAI"))]
assert not leaked, f"environment leaked into the worker: {leaked}"
if len(sys.argv) > 3:
    with open(sys.argv[3], "a") as f:
        f.write("call\\n")
z = np.load(sys.argv[1])
ohlcv, H, Q = z["ohlcv"], [int(h) for h in z["horizons"]], z["quantiles"]
r = np.diff(np.log(ohlcv[:, :, 3]), axis=1)[:, -20:]
sd = r.std(axis=1, ddof=1)
cube = np.stack([sd[:, None] * np.sqrt(h) * norm.ppf(Q)[None, :] for h in H], axis=1)
np.savez(sys.argv[2], cube=cube)
'''


def spec(worker, **kw):
    return ModelSpec(name="stub", release="2020-06-01", context_len=64, worker=str(worker), requirements=["numpy"], repos=[], stride=5, batch=20, **kw)


def stub(tmp_path, body=WORKER, **kw):
    w = tmp_path / "worker.py"
    w.write_text(body)
    return SubprocessForecaster(spec(w, **kw), launcher=[sys.executable, "-I"])


def test_a_worker_process_round_trips_and_matches_the_in_process_forecaster(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("GETRICH_SECRET", "x")
    bars = make_bars(300)
    sp = stub(tmp_path)
    generate(sp, "A", bars)
    got = load_cache("stub", "A")
    ref = RandomWalk()
    generate(ref, "A", bars, stride=5)
    want = load_cache("fake_rw", "A")
    np.testing.assert_array_equal(got.origins, want.origins)
    np.testing.assert_allclose(got.cube, want.cube, atol=1e-6)


def test_the_worker_gets_no_secrets_and_no_network_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    bars = make_bars(150)
    generate(stub(tmp_path), "A", bars, max_new=5)                  # the worker asserts on its own environment and exits non-zero if it leaks
    assert len(load_cache("stub", "A")) == 5


def test_a_failing_worker_raises_with_its_error_and_caches_nothing(tmp_path):
    bad = stub(tmp_path, "import sys\nprint('boom: model file missing', file=sys.stderr)\nsys.exit(3)\n")
    with pytest.raises(RuntimeError, match="boom: model file missing"):
        generate(bad, "A", make_bars(150), max_new=3)
    assert load_cache("stub", "A") is None


def test_a_worker_that_returns_garbage_is_rejected(tmp_path):
    nan = stub(tmp_path, "import sys, numpy as np\nz = np.load(sys.argv[1])\nnp.savez(sys.argv[2], cube=np.full((len(z['ohlcv']), 3, 5), np.nan))\n")
    with pytest.raises(ValueError, match="non-finite"):
        generate(nan, "A", make_bars(150), max_new=3)
    wrong = stub(tmp_path, "import sys, numpy as np\nz = np.load(sys.argv[1])\nnp.savez(sys.argv[2], cube=np.zeros((1, 2, 2)))\n")
    with pytest.raises(ValueError, match="shape"):
        generate(wrong, "A", make_bars(150), max_new=3)


def test_the_worker_is_called_once_per_batch_not_once_per_origin(tmp_path):
    counter = tmp_path / "calls.txt"
    sp = stub(tmp_path, extra_args=[str(counter)])
    bars = make_bars(200)
    generate(sp, "A", bars)                                         # spec batch is 20
    n = len(load_cache("stub", "A"))
    assert len(counter.read_text().split()) == math.ceil(n / 20)


def test_every_registered_model_has_a_worker_a_release_date_and_pinned_repos():
    assert set(models.SPECS) == {"kronos_small", "chronos2", "timesfm25"}
    for name, sp in models.SPECS.items():
        assert (WORKERS / sp.worker).exists() and sp.repos and sp.requirements
        py_compile.compile(str(WORKERS / sp.worker), doraise=True)    # at least valid Python, until the real weights are fetched
        assert all(r["repo"].split("/")[0] in ("amazon", "google", "NeoQuasar") for r in sp.repos)
        assert all("*.bin" not in r["allow"] and "*.pt" not in r["allow"] and "*.pkl" not in r["allow"] for r in sp.repos)   # safetensors only
    assert not any("timesfm-3" in r["repo"] for sp in models.SPECS.values() for r in sp.repos)       # TimesFM 3.0 weights are non-commercial


def test_the_real_worker_command_uses_an_isolated_uv_environment_with_the_models_requirements():
    fc = models.get("chronos2")
    cmd = fc.command(WORKERS / "in.npz", WORKERS / "out.npz")
    assert cmd[:4] == ["uv", "run", "--no-project", "--python"] and "chronos-forecasting>=2.0" in cmd and "python" in cmd and "-I" in cmd
    assert models.get("kronos_small")._env["KRONOS_SRC"].endswith("models/kronos-src")


# ------------------------------------------------------------------ the lock file


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "config").mkdir(parents=True)
    monkeypatch.setenv("GETRICH_HOME", str(h))
    return h


def test_verify_catches_unfetched_missing_and_tampered_weights(home, tmp_path):
    assert "not fetched" in fetch.verify("chronos2")[0]
    wdir = tmp_path / "snap"
    wdir.mkdir()
    (wdir / "model.safetensors").write_bytes(b"weights" * 1000)
    e = fetch.file_entry(wdir / "model.safetensors")
    (home / "config" / "forecast_models.lock.json").write_text(json.dumps(
        {"chronos2": {"repos": {"amazon/chronos-2": {"path": str(wdir), "revision": "abc", "files": [{"name": "model.safetensors", **e}]}}}}))
    assert fetch.verify("chronos2") == []
    (wdir / "model.safetensors").write_bytes(b"tampered" * 1000)
    assert "does not match" in fetch.verify("chronos2")[0]
    (wdir / "model.safetensors").unlink()
    assert "missing" in fetch.verify("chronos2")[0]


def test_forecast_run_refuses_to_start_without_fetched_weights(home, capsys):
    assert cli.main(["forecast-run", "chronos2"]) == 2
    assert "not fetched" in capsys.readouterr().out


def test_kronos_also_refuses_until_its_source_is_marked_reviewed(home, capsys, tmp_path):
    wdir = tmp_path / "snap"
    wdir.mkdir()
    (wdir / "model.safetensors").write_bytes(b"x")
    e = fetch.file_entry(wdir / "model.safetensors")
    repos = {r["repo"]: {"path": str(wdir), "revision": "abc", "files": [{"name": "model.safetensors", **e}]} for r in models.SPECS["kronos_small"].repos}
    lock = {"kronos_small": {"repos": repos}, "kronos_code": {"commit": "abc", "reviewed": False}}
    (home / "config" / "forecast_models.lock.json").write_text(json.dumps(lock))
    assert cli.main(["forecast-run", "kronos_small"]) == 2 and "reviewed" in capsys.readouterr().out
