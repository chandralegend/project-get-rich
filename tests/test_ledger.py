import json
from datetime import timedelta

import pytest

from getrich.obs.events import utcnow
from getrich.store import ledger
from getrich.store.db import connect


def _news(con, item_id, ingested):
    con.execute(
        "INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?)",
        [item_id, "test", "https://x", "title", "", None, ingested, item_id + "-hash"],
    )


def _two_insights(con):
    _news(con, "n_a", utcnow() - timedelta(minutes=5))
    ledger.record_insight(con, asset="ETH", payload={"direction": "risk_on"}, evidence=["n_a"], model="haiku")
    ledger.record_insight(con, asset="BTC", payload={"direction": "risk_off"}, evidence=["n_a"], model="haiku")


def test_empty_ledger_verifies():
    with connect() as con:
        assert ledger.verify_chain(con) == (True, 0, None)


def test_chain_grows_links_and_verifies():
    with connect() as con:
        _two_insights(con)
        assert ledger.verify_chain(con) == (True, 2, None)
        rows = con.execute("SELECT seq, prev_hash, hash FROM insights ORDER BY seq").fetchall()
        assert rows[0][1] == ledger.GENESIS
        assert rows[1][1] == rows[0][2]  # second row points at the first row's hash
        assert ledger.count_insights(con) == 2


def test_editing_a_past_insight_is_detected():
    with connect() as con:
        _two_insights(con)
        con.execute("UPDATE insights SET payload = ? WHERE seq = 1", [json.dumps({"direction": "flipped"})])
        ok, _, bad = ledger.verify_chain(con)
        assert ok is False and bad == 1


def test_deleting_a_row_is_detected():
    with connect() as con:
        _two_insights(con)
        con.execute("DELETE FROM insights WHERE seq = 1")
        ok, _, bad = ledger.verify_chain(con)
        assert ok is False and bad == 2


def test_look_ahead_is_refused():
    with connect() as con:
        _news(con, "n_late", utcnow() - timedelta(minutes=5))
        with pytest.raises(ValueError, match="look-ahead"):
            ledger.record_insight(
                con, asset="ETH", payload={"d": 1}, evidence=["n_late"], model="haiku",
                as_of=utcnow() - timedelta(hours=2),  # decision clock earlier than the news arrived
            )
        assert ledger.count_insights(con) == 0


def test_unknown_or_missing_evidence_is_refused():
    with connect() as con:
        with pytest.raises(ValueError, match="unknown evidence"):
            ledger.record_insight(con, asset="ETH", payload={"d": 1}, evidence=["n_nope"], model="haiku")
        with pytest.raises(ValueError, match="at least one"):
            ledger.record_insight(con, asset="ETH", payload={"d": 1}, evidence=[], model="haiku")
        with pytest.raises(ValueError, match="non-empty"):
            ledger.record_insight(con, asset="ETH", payload={}, evidence=["n_a"], model="haiku")
