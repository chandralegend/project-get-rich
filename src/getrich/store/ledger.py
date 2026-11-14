"""Immutable, hash-chained insight ledger (ARCHITECTURE.md 4.2).

Every insight the agent layer produces is appended here once and never edited. Each row stores the
SHA-256 of the previous row plus its own content, so changing, deleting or reordering any past row
breaks every hash after it, and verify_chain() finds it. The watchdog verifies the chain.

Two integrity rules are enforced at write time:
  * every cited evidence id must exist in news_items, and
  * an insight may not cite news ingested AFTER its `as_of` time (no look-ahead).

Callers pass an open connection (from store.db.connect); do not call connect() inside another
connect() block, the cross-process lock is not re-entrant.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import duckdb

from ..ids import new_id
from ..obs.events import emit, utcnow

GENESIS = "0" * 64

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS insights (
    seq BIGINT PRIMARY KEY,
    insight_id VARCHAR UNIQUE,
    as_of TIMESTAMPTZ,          -- decision clock: only data ingested at or before this may have been used
    recorded_at TIMESTAMPTZ,
    asset VARCHAR,
    model VARCHAR,
    evidence JSON,              -- list of news item_ids
    payload JSON,               -- the structured insight (event type, direction, horizon, confidence, ...)
    prev_hash VARCHAR,
    hash VARCHAR
);
"""


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def compute_hash(prev_hash: str, insight_id: str, as_of: datetime, recorded_at: datetime,
                 asset: str, model: str, evidence: list[str], payload: dict) -> str:
    body = _canonical(
        {
            "insight_id": insight_id,
            "as_of": _utc_iso(as_of),
            "recorded_at": _utc_iso(recorded_at),
            "asset": asset,
            "model": model,
            "evidence": evidence,
            "payload": payload,
        }
    )
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def record_insight(
    con: duckdb.DuckDBPyConnection,
    *,
    asset: str,
    payload: dict,
    evidence: list[str],
    model: str,
    as_of: datetime | None = None,
    decision_id: str | None = None,
) -> str:
    """Append one insight. Returns its insight_id. Raises ValueError on a broken integrity rule."""
    con.execute(LEDGER_SCHEMA)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("payload must be a non-empty dict")
    if not evidence:
        raise ValueError("an insight must cite at least one evidence item")
    recorded_at = utcnow()
    as_of = (as_of or recorded_at).astimezone(timezone.utc)
    if as_of > recorded_at:
        raise ValueError("as_of cannot be in the future")

    rows = con.execute(
        "SELECT item_id, ingested_at FROM news_items WHERE item_id IN ({})".format(",".join("?" * len(evidence))),
        list(evidence),
    ).fetchall()
    found = {item_id: ingested for item_id, ingested in rows}
    missing = [e for e in evidence if e not in found]
    if missing:
        raise ValueError(f"unknown evidence ids: {missing}")
    late = [e for e, ing in found.items() if ing > as_of]
    if late:
        raise ValueError(f"look-ahead: evidence ingested after as_of: {late}")

    last = con.execute("SELECT seq, hash FROM insights ORDER BY seq DESC LIMIT 1").fetchone()
    seq, prev_hash = (last[0] + 1, last[1]) if last else (1, GENESIS)
    insight_id = new_id("i")
    digest = compute_hash(prev_hash, insight_id, as_of, recorded_at, asset, model, list(evidence), payload)
    con.execute(
        "INSERT INTO insights VALUES (?,?,?,?,?,?,?,?,?,?)",
        [seq, insight_id, as_of, recorded_at, asset, model, json.dumps(list(evidence)), json.dumps(payload), prev_hash, digest],
    )
    emit("insight.recorded", service="ledger", decision_id=decision_id, insight_id=insight_id,
         seq=seq, asset=asset, model=model, evidence=list(evidence), hash=digest)
    return insight_id


def verify_chain(con: duckdb.DuckDBPyConnection) -> tuple[bool, int, int | None]:
    """Recompute every hash in order. Returns (ok, rows_checked, first_bad_seq)."""
    con.execute(LEDGER_SCHEMA)
    prev = GENESIS
    expected_seq = 1
    count = 0
    for seq, insight_id, as_of, recorded_at, asset, model, evidence, payload, prev_hash, digest in con.execute(
        "SELECT seq, insight_id, as_of, recorded_at, asset, model, evidence, payload, prev_hash, hash "
        "FROM insights ORDER BY seq"
    ).fetchall():
        count += 1
        if seq != expected_seq or prev_hash != prev:
            return False, count, seq
        want = compute_hash(prev, insight_id, as_of, recorded_at, asset, model, json.loads(evidence), json.loads(payload))
        if want != digest:
            return False, count, seq
        prev = digest
        expected_seq += 1
    return True, count, None


def count_insights(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(LEDGER_SCHEMA)
    return con.execute("SELECT count(*) FROM insights").fetchone()[0]
