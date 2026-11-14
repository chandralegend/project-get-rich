"""Per-service heartbeat files. A heartbeat records the last run and the last SUCCESSFUL run."""

from __future__ import annotations

import json
import os
from typing import Any

from .. import config
from .events import emit, iso, utcnow


def beat(service: str, ok: bool = True, **info: Any) -> None:
    config.heartbeat_dir().mkdir(parents=True, exist_ok=True)
    path = config.heartbeat_dir() / f"{service}.json"
    prev = read(service) or {}
    now = iso(utcnow())
    rec = {
        "service": service,
        "ts": now,
        "ok": ok,
        "last_ok_ts": now if ok else prev.get("last_ok_ts"),
        "info": info,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, default=str))
    os.replace(tmp, path)
    emit("service.heartbeat", service=service, ok=ok)


def read(service: str) -> dict[str, Any] | None:
    path = config.heartbeat_dir() / f"{service}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
