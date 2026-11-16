import os
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from getrich.forecast import base, fetch, live, models
from getrich.forecast.base import load_cache
from getrich.forecast.fakes import RandomWalk
from getrich.forecast.generate import generate
from getrich.obs.events import utcnow
from getrich.ops import scheduler
from getrich.store.db import connect


def seed_daily(days=200, newest_back=1):
    """Daily bars for BTC and ETH; the newest closed bar is `newest_back` days ago."""
    rng = np.random.default_rng(3)
    now = utcnow()
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=newest_back - 1) - timedelta(days=1)
    with connect() as con:
        for sym, base_p in (("BTCUSDT", 60000.0), ("ETHUSDT", 2000.0)):
            d = base_p * np.cumprod(1 + rng.normal(0.0005, 0.02, days))
            con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            [("binance", sym, "1d", end - timedelta(days=days - 1 - i), p, p * 1.01, p * 0.99, p, 100.0, 1.0, 1, now) for i, p in enumerate(d)])


class Rw(RandomWalk):
    name = "chronos2"                                   # the registry name the live run looks the cache up by
    calls = 0

    def forecast(self, ohlcv, ts):
        Rw.calls += 1
        return super().forecast(ohlcv, ts)


@pytest.fixture(autouse=True)
def weights_ok(monkeypatch):
    monkeypatch.setattr(fetch, "verify", lambda name: [])
    monkeypatch.setattr(fetch, "verify_code", lambda: [])
    Rw.calls = 0


def bars_of(sym):
    from getrich.eval.data import load_bars
    return load_bars(sym, "1d")


def test_the_newest_bar_gets_exactly_one_new_origin_and_history_is_untouched():
    seed_daily()
    for s in ("BTCUSDT", "ETHUSDT"):
        generate(Rw(), s, bars_of(s).iloc[:-3], stride=5)                      # an older, stride-5 history, as the research cache has
    before = {s: len(load_cache("chronos2", s)) for s in ("BTCUSDT", "ETHUSDT")}
    out = live.run(("chronos2",), forecaster=lambda n: Rw())
    assert out["ok"] and [r["status"] for r in out["results"]] == ["new", "new"]
    for s in ("BTCUSDT", "ETHUSDT"):
        c = load_cache("chronos2", s)
        assert len(c) == before[s] + 1 and pd.Timestamp(c.origins.max()).tz_localize("UTC") == bars_of(s).index[-1]


def test_running_again_does_nothing_until_a_new_daily_bar_exists():
    seed_daily()
    live.run(("chronos2",), forecaster=lambda n: Rw())
    calls = Rw.calls
    out = live.run(("chronos2",), forecaster=lambda n: Rw())
    assert [r["status"] for r in out["results"]] == ["up_to_date", "up_to_date"] and Rw.calls == calls


def test_a_failing_model_is_reported_and_the_others_still_run():
    seed_daily()

    def pick(name):
        if name == "timesfm25":
            raise RuntimeError("worker crashed")
        return Rw()

    out = live.run(("timesfm25", "chronos2"), forecaster=pick)
    by = {(r["model"], r["symbol"]): r for r in out["results"]}
    assert not out["ok"] and by[("timesfm25", "BTCUSDT")]["status"] == "failed" and "worker crashed" in by[("timesfm25", "BTCUSDT")]["error"]
    assert by[("chronos2", "BTCUSDT")]["status"] == "new"


def test_weights_that_do_not_match_the_lock_are_never_run(monkeypatch):
    seed_daily()
    monkeypatch.setattr(fetch, "verify", lambda name: ["model.safetensors does not match the recorded hash"])
    out = live.run(("chronos2",), forecaster=lambda n: pytest.fail("a worker must not start on unverified weights"))
    assert not out["ok"] and out["results"][0]["status"] == "refused"
    assert load_cache("chronos2", "BTCUSDT") is None


def test_status_reports_how_far_behind_the_newest_bar_each_forecast_is():
    seed_daily()
    generate(Rw(), "BTCUSDT", bars_of("BTCUSDT").iloc[:-3], stride=1)
    st = {(r["model"], r["symbol"]): r for r in live.status(names=("chronos2",))}
    assert st[("chronos2", "BTCUSDT")]["days_behind"] == 3 and st[("chronos2", "ETHUSDT")]["newest_origin"] is None


def test_a_cache_is_written_aside_and_renamed_so_a_reader_never_sees_half_a_file():
    seed_daily()
    generate(Rw(), "BTCUSDT", bars_of("BTCUSDT"), stride=7)
    folder = base.cache_path("chronos2", "BTCUSDT").parent
    assert [p.name for p in folder.iterdir()] == ["BTCUSDT.npz"]


def test_the_models_container_picks_its_prepared_python_and_finds_weights_under_hf_home(monkeypatch, tmp_path):
    monkeypatch.setenv("GETRICH_FORECAST_PYTHON", "/opt/env/bin/python")
    fc = models.get("chronos2")
    assert fc.command(tmp_path / "i.npz", tmp_path / "o.npz")[:2] == ["/opt/env/bin/python", "-I"]
    monkeypatch.setenv("HF_HOME", "/hf")
    got = fetch.snapshot_dir("amazon/chronos-2", {"path": "/Users/someone/.cache/does/not/exist", "revision": "abc123"})
    assert str(got) == "/hf/hub/models--amazon--chronos-2/snapshots/abc123"


def test_the_main_scheduler_never_carries_the_model_job_and_the_models_one_does():
    assert not any(j.name == "forecast-live" for j in scheduler.JOBS)
    assert [j.name for j in scheduler.MODEL_JOBS] == ["forecast-live"] and not any(a in ("trader", "approve", "propose") for j in scheduler.MODEL_JOBS for a in j.args)


def test_the_two_schedulers_keep_separate_state_files_and_read_all_merges_them():
    scheduler._write_state("watchdog", ok=True)
    old = scheduler._state_name
    try:
        scheduler._state_name = "scheduler-models"
        scheduler._write_state("forecast-live", ok=True, seconds=1.0)
    finally:
        scheduler._state_name = old
    allstate = scheduler.read_all()
    assert {"watchdog", "forecast-live"} <= set(allstate["jobs"]) and allstate["models_heartbeat"]
    assert "forecast-live" not in scheduler.read_state("scheduler")["jobs"]
