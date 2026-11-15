import json
import sys
from datetime import datetime

from getrich import config
from getrich.ops import scheduler
from getrich.ops.scheduler import Job


def test_a_job_runs_as_a_subprocess_and_its_result_is_recorded(monkeypatch):
    monkeypatch.setattr(sys, "executable", sys.executable)
    ok = scheduler.run_once(Job("selftest-ok", ("--help",), every_s=60, timeout_s=60))
    assert ok == 0
    state = scheduler.read_state()["jobs"]["selftest-ok"]
    assert state["ok"] is True and state["running"] is False and state["exit_code"] == 0
    assert (config.logs_dir() / "job-selftest-ok.log").read_text().startswith("\n--- ")


def test_a_failing_job_is_recorded_not_raised():
    bad = scheduler.run_once(Job("selftest-bad", ("no-such-command",), every_s=60, timeout_s=60))
    assert bad != 0 and scheduler.read_state()["jobs"]["selftest-bad"]["ok"] is False


def test_a_hung_job_is_stopped_at_its_timeout(monkeypatch):
    import subprocess

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)
    monkeypatch.setattr(scheduler.subprocess, "run", hang)
    assert scheduler.run_once(Job("selftest-hang", ("watchdog",), every_s=60, timeout_s=1)) == 124


def test_daily_jobs_wait_for_the_next_occurrence():
    assert scheduler._seconds_until((6, 0), datetime(2026, 11, 15, 5, 0)) == 3600
    assert scheduler._seconds_until((6, 0), datetime(2026, 11, 15, 6, 0)) == 86400
    assert scheduler._seconds_until((7, 0), datetime(2026, 11, 15, 23, 0)) == 8 * 3600


def test_the_schedule_mirrors_the_launchd_jobs_and_never_includes_the_trader_or_orders():
    names = {j.name for j in scheduler.JOBS}
    assert {"watchdog", "paper-tick", "refresh-data", "collect-news", "collect-webnews", "agents-extract", "agents-briefing", "agents-score"} <= names
    assert not any(a in ("trader", "approve", "propose", "kill") for j in scheduler.JOBS for a in j.args)
    heavy = [j for j in scheduler.JOBS if j.serial]
    assert heavy and not any(j.name in ("watchdog", "paper-tick") for j in heavy)
