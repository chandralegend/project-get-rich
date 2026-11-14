import json

from getrich import config
from getrich.ids import new_id
from getrich.obs.events import emit
from getrich.obs.heartbeat import beat, read
from getrich.obs.ingest import ingest_events
from getrich.store.db import connect


def test_emit_writes_jsonl_with_decision_id():
    did = new_id("d")
    emit("model.scored", service="test", decision_id=did, p_win=0.58)
    files = list(config.logs_dir().glob("events-*.jsonl"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text().splitlines()[0])
    assert rec["event"] == "model.scored"
    assert rec["decision_id"] == did
    assert rec["data"]["p_win"] == 0.58


def test_ids_are_prefixed_and_unique_and_sortable():
    a, b = new_id("n"), new_id("n")
    assert a.startswith("n_") and a != b
    assert len(a) == len(b)


def test_ingest_is_incremental_and_idempotent():
    emit("a", service="t")
    emit("b", service="t")
    with connect() as con:
        assert ingest_events(con) == 2
        assert ingest_events(con) == 0  # nothing new
        emit("c", service="t")
        assert ingest_events(con) == 1
        assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 3


def test_ingest_ignores_partial_trailing_line():
    emit("a", service="t")
    path = next(config.logs_dir().glob("events-*.jsonl"))
    with open(path, "ab") as f:
        f.write(b'{"ts":"2026-01-01T00:00:00Z","event":"partial"')  # no newline yet
    with connect() as con:
        assert ingest_events(con) == 1


def test_heartbeat_keeps_last_ok_when_a_run_fails():
    beat("svc", ok=True)
    first_ok = read("svc")["last_ok_ts"]
    beat("svc", ok=False)
    hb = read("svc")
    assert hb["ok"] is False
    assert hb["last_ok_ts"] == first_ok


def test_nested_database_access_fails_fast_with_a_clear_message_instead_of_hanging():
    import time

    import pytest

    start = time.monotonic()
    with connect():
        with pytest.raises(RuntimeError, match="not re-entrant"):
            with connect():
                pass
    assert time.monotonic() - start < 5        # not the 30-second lock timeout
    with connect():                              # and the lock is released afterwards
        pass
