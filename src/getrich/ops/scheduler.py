"""The scheduler: runs the same jobs the launchd plists run, inside the container, so the whole system lives in Docker.

Each job is the same `getrich` command a launchd job would run, started as a subprocess so a crash or hang in one cannot take the others down.
Output goes to data/logs/<job>.log. The state of every job (last start, last end, exit code, how long) is written to data/state/scheduler.json for
the status screens. Jobs that write the store and call the network (collectors, news, agents) share one lock and run one at a time; the watchdog and
paper tick are short and run on their own so a slow collector can never delay them.

Not scheduled on purpose: the trader (manual only, by the owner's choice), anything that places or approves orders, and host-only things such as
keeping the Mac awake (caffeinate stays a host job: a container cannot stop the host from sleeping).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from .. import config
from ..obs.events import emit, iso, utcnow

SERVICE = "ops.scheduler"
LOG_CAP_BYTES = 2_000_000


@dataclass(frozen=True)
class Job:
    name: str
    args: tuple[str, ...]
    every_s: int | None = None          # run this often, counted from the end of the previous run
    daily_at: tuple[int, int] | None = None   # or once a day at local (hour, minute); the container's TZ decides what local means
    serial: bool = True                 # shares the one heavy-job lock
    on_start: bool = True               # run once when the scheduler starts (launchd RunAtLoad)
    timeout_s: int = 3600


JOBS: tuple[Job, ...] = (
    Job("watchdog", ("watchdog",), every_s=60, serial=False, timeout_s=120),
    Job("paper-tick", ("paper-tick",), every_s=3600, serial=False, timeout_s=300),
    Job("refresh-data", ("refresh-data",), every_s=3600, timeout_s=1800),
    Job("collect-news", ("collect-news",), every_s=3600, timeout_s=900),
    Job("collect-webnews", ("collect-webnews",), every_s=3600, timeout_s=1800),
    Job("agents-extract", ("agents-extract", "--limit", "80"), every_s=3600, timeout_s=1800),
    Job("agents-briefing", ("agents-briefing",), daily_at=(6, 0), on_start=False, timeout_s=900),
    Job("agents-score", ("agents-score",), daily_at=(7, 0), on_start=False, timeout_s=900),
)

_serial = threading.Lock()
_state_lock = threading.Lock()


def state_path():
    return config.state_dir() / "scheduler.json"


def read_state() -> dict:
    try:
        return json.loads(state_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(name: str, **fields) -> None:
    with _state_lock:
        state = read_state()
        state.setdefault("jobs", {}).setdefault(name, {}).update(fields)
        state["heartbeat"] = iso(utcnow())
        config.ensure_dirs()
        tmp = state_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(state, default=str))
        os.replace(tmp, state_path())


def _cap_log(path) -> None:
    try:
        if path.stat().st_size > LOG_CAP_BYTES:
            tail = path.read_bytes()[-LOG_CAP_BYTES // 2:]
            path.write_bytes(tail)
    except OSError:
        pass


def run_once(job: Job) -> int:
    """Run one job to completion (or its timeout) and record the result. Returns the exit code (124 on timeout)."""
    config.ensure_dirs()
    log = config.logs_dir() / f"job-{job.name}.log"
    _cap_log(log)
    started = time.monotonic()
    _write_state(job.name, running=True, last_start=iso(utcnow()), args=list(job.args))
    code = 1
    try:
        with open(log, "ab") as fh:
            fh.write(f"\n--- {iso(utcnow())} getrich {' '.join(job.args)}\n".encode())
            fh.flush()
            try:
                proc = subprocess.run([sys.executable, "-m", "getrich.cli", *job.args], stdout=fh, stderr=subprocess.STDOUT, timeout=job.timeout_s, env=os.environ.copy())
                code = proc.returncode
            except subprocess.TimeoutExpired:
                code = 124
                fh.write(f"timed out after {job.timeout_s}s\n".encode())
    except Exception as exc:                                              # the scheduler itself must never die on one job
        emit("scheduler.error", service=SERVICE, level="error", job=job.name, error=repr(exc)[:300])
    took = round(time.monotonic() - started, 1)
    _write_state(job.name, running=False, last_end=iso(utcnow()), exit_code=code, seconds=took, ok=code == 0)
    emit("scheduler.run", service=SERVICE, level="info" if code == 0 else "warn", job=job.name, exit_code=code, seconds=took)
    return code


def _seconds_until(daily_at: tuple[int, int], now: datetime | None = None) -> float:
    now = now or datetime.now()
    target = now.replace(hour=daily_at[0], minute=daily_at[1], second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _loop(job: Job, stop: threading.Event) -> None:
    first = True
    while not stop.is_set():
        if job.daily_at is not None:
            if stop.wait(_seconds_until(job.daily_at)):
                return
        elif not (first and job.on_start):
            if stop.wait(job.every_s):
                return
        first = False
        if job.serial:
            with _serial:
                run_once(job)
        else:
            run_once(job)


def run_forever(jobs: tuple[Job, ...] = JOBS) -> None:
    """Block until interrupted. One thread per job; each sleeps on its own schedule."""
    stop = threading.Event()
    emit("scheduler.started", service=SERVICE, jobs=[j.name for j in jobs])
    threads = [threading.Thread(target=_loop, args=(j, stop), name=j.name, daemon=True) for j in jobs]
    for i, t in enumerate(threads):
        t.start()
        time.sleep(2 if jobs[i].serial else 0)                            # stagger the heavy jobs a little at start
    try:
        while True:
            time.sleep(5)
            _write_state("_alive", running=True)
    except KeyboardInterrupt:
        stop.set()
