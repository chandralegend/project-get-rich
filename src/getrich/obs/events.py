"""Append-only structured event log (the source of truth for observability).

One JSON object per line in data/logs/events-YYYY-MM-DD.jsonl:
  ts, event, service, level, decision_id, item_id, data{...}
Writes use O_APPEND so concurrent processes can append whole lines safely.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from .. import config


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def emit(
    event: str,
    *,
    service: str,
    level: str = "info",
    decision_id: str | None = None,
    item_id: str | None = None,
    **data: Any,
) -> dict[str, Any]:
    """Write one event. Returns the record. Never raises on serialisation of odd values (uses str())."""
    now = utcnow()
    rec = {
        "ts": iso(now),
        "event": event,
        "service": service,
        "level": level,
        "decision_id": decision_id,
        "item_id": item_id,
        "data": data,
    }
    line = (json.dumps(rec, separators=(",", ":"), default=str) + "\n").encode()
    config.logs_dir().mkdir(parents=True, exist_ok=True)
    path = config.logs_dir() / f"events-{now:%Y-%m-%d}.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    return rec
