"""DuckDB store with a cross-process write lock.

DuckDB allows one read-write process at a time, and several launchd jobs share this file, so every
access goes through connect(), which holds an flock for the duration of the `with` block. Keep the
block short: never do network calls while holding it.
"""

from __future__ import annotations

import contextlib
import fcntl
import threading
import time
from collections.abc import Iterator

import duckdb

from .. import config
from .ledger import LEDGER_SCHEMA

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    venue VARCHAR, symbol VARCHAR, timeframe VARCHAR, ts_open TIMESTAMPTZ,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    volume DOUBLE, quote_volume DOUBLE, trades BIGINT,
    ingested_at TIMESTAMPTZ,
    PRIMARY KEY (venue, symbol, timeframe, ts_open)
);
CREATE TABLE IF NOT EXISTS news_items (
    item_id VARCHAR PRIMARY KEY, source VARCHAR, url VARCHAR, title VARCHAR, summary VARCHAR,
    published_at TIMESTAMPTZ,   -- the source's own claim, may be missing or wrong
    ingested_at TIMESTAMPTZ,    -- our clock: backtests may only use this one
    content_hash VARCHAR UNIQUE
);
CREATE TABLE IF NOT EXISTS item_processing (
    item_id VARCHAR PRIMARY KEY,
    status VARCHAR,             -- processed | skipped_irrelevant | duplicate | model_irrelevant | failed | refused
    detail VARCHAR,
    processed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS insight_outcomes (
    insight_id VARCHAR PRIMARY KEY,
    resolved_at TIMESTAMPTZ,
    horizon_days INTEGER,
    realized_return DOUBLE,
    hit BOOLEAN,
    detail VARCHAR
);
"""


@contextlib.contextmanager
def connect(timeout: float = 30.0) -> Iterator[duckdb.DuckDBPyConnection]:
    if getattr(_local, "held", False):
        raise RuntimeError("nested connect(): the database lock is not re-entrant. Read, compute and write in separate blocks.")
    config.ensure_dirs()
    lock_path = config.state_dir() / ".db.lock"
    with open(lock_path, "w") as lock_file:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError("could not get the database lock") from None
                time.sleep(0.2)
        con = duckdb.connect(str(config.db_path()))
        _local.held = True
        try:
            con.execute(SCHEMA)
            con.execute(LEDGER_SCHEMA)
            yield con
        finally:
            _local.held = False
            con.close()
            fcntl.flock(lock_file, fcntl.LOCK_UN)
