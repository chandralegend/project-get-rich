"""Background jobs started from the web UI (a trader run, a data refresh). Each is a `getrich` subprocess with its own log, one at a time per kind.

State lives in data/state/jobs/<id>.json so a restart of the API does not lose the history. A job the API started is waited on by a thread that
records the exit code; if the API restarts mid-job the record says `lost` once its process is gone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from .. import config
from ..ids import new_id
from ..obs.events import emit, iso, utcnow

ALLOWED = {"trader", "refresh-data"}
_procs: dict[str, subprocess.Popen] = {}


def jobs_dir() -> Path:
    d = config.state_dir() / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def _write(meta: dict) -> None:
    tmp = _meta_path(meta["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(meta))
    os.replace(tmp, _meta_path(meta["id"]))


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def get(job_id: str) -> dict | None:
    try:
        meta = json.loads(_meta_path(job_id).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if meta.get("status") == "running" and job_id not in _procs and not _pid_alive(meta.get("pid")):
        meta["status"] = "lost"
    return meta


def list_jobs(limit: int = 20) -> list[dict]:
    ids = sorted((p.stem for p in jobs_dir().glob("*.json")), reverse=True)[:limit]
    return [m for m in (get(i) for i in ids) if m]


def running(kind: str) -> dict | None:
    return next((m for m in list_jobs(50) if m["kind"] == kind and m["status"] == "running"), None)


def tail(job_id: str, lines: int = 80) -> str:
    meta = get(job_id)
    if not meta:
        return ""
    try:
        return "\n".join(Path(meta["log"]).read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def start(kind: str, args: list[str]) -> dict:
    """Start a job. Raises ValueError for an unknown kind and RuntimeError if one of that kind is already running."""
    if kind not in ALLOWED:
        raise ValueError(f"unknown job kind {kind!r}")
    if (cur := running(kind)):
        raise RuntimeError(f"a {kind} job is already running ({cur['id']})")
    job_id = new_id("j")
    log = config.logs_dir() / f"job-{job_id}.log"
    config.ensure_dirs()
    fh = open(log, "ab")
    proc = subprocess.Popen([sys.executable, "-m", "getrich.cli", kind, *args], stdout=fh, stderr=subprocess.STDOUT, start_new_session=True, env=os.environ.copy())
    meta = {"id": job_id, "kind": kind, "args": args, "pid": proc.pid, "status": "running", "started": iso(utcnow()), "finished": None, "exit_code": None, "log": str(log)}
    _write(meta)
    _procs[job_id] = proc

    def waiter():
        code = proc.wait()
        fh.close()
        m = get(job_id) or meta
        m.update(status="done" if code == 0 else "failed", exit_code=code, finished=iso(utcnow()))
        _write(m)
        _procs.pop(job_id, None)
        emit("api.job_finished", service="api", job=kind, job_id=job_id, exit_code=code)

    threading.Thread(target=waiter, daemon=True).start()
    emit("api.job_started", service="api", job=kind, job_id=job_id, args=args)
    return meta
