"""Load the JSONL event log into the DuckDB `events` table, incrementally and idempotently."""

from __future__ import annotations

import json

import duckdb

from .. import config

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    ts TIMESTAMPTZ, event VARCHAR, service VARCHAR, level VARCHAR,
    decision_id VARCHAR, item_id VARCHAR, data JSON
);
CREATE TABLE IF NOT EXISTS events_cursor (file VARCHAR PRIMARY KEY, byte_offset BIGINT);
"""


def ingest_events(con: duckdb.DuckDBPyConnection) -> int:
    """Append new complete lines from every events-*.jsonl file. Returns rows added."""
    con.execute(EVENTS_SCHEMA)
    added = 0
    for path in sorted(config.logs_dir().glob("events-*.jsonl")):
        row = con.execute("SELECT byte_offset FROM events_cursor WHERE file = ?", [path.name]).fetchone()
        offset = row[0] if row else 0
        size = path.stat().st_size
        if size <= offset:
            continue
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(size - offset)
        end = chunk.rfind(b"\n")
        if end < 0:
            continue  # only a partial line so far
        rows = []
        for line in chunk[: end + 1].decode("utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
                rows.append(
                    (
                        r["ts"],
                        r["event"],
                        r.get("service"),
                        r.get("level"),
                        r.get("decision_id"),
                        r.get("item_id"),
                        json.dumps(r.get("data") or {}),
                    )
                )
            except (json.JSONDecodeError, KeyError):
                continue  # skip a corrupt line, keep going
        if rows:
            con.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        con.execute(
            "INSERT OR REPLACE INTO events_cursor VALUES (?, ?)", [path.name, offset + end + 1]
        )
        added += len(rows)
    return added
