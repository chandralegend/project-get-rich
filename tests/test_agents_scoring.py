import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from getrich.agents import scoring
from getrich.obs.events import utcnow
from getrich.store.db import connect
from getrich.store.ledger import record_insight

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def seed(con, closes, symbol="BTCUSDT"):
    rows = [("binance", symbol, "1d", START + timedelta(days=i), c, c, c, c, 1.0, 1.0, 1, utcnow()) for i, c in enumerate(closes)]
    con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def issue(con, kind, asset, as_of, **payload):
    con.execute("INSERT OR IGNORE INTO news_items VALUES ('n1','s','u','t','',NULL,?, 'h')", [START])
    return record_insight(con, asset=asset, evidence=["n1"], model="claude-sonnet-5-5", as_of=as_of, payload={"kind": kind, **payload})


def noisy_uptrend(n=60, drift=0.01, seed=0):
    rng = np.random.default_rng(seed)
    return list(100 * np.cumprod(1 + drift + rng.normal(0, 0.003, n)))


def outcome(con, insight_id):
    return con.execute("SELECT horizon_days, realized_return, hit FROM insight_outcomes WHERE insight_id = ?", [insight_id]).fetchone()


def test_views_are_resolved_only_after_the_horizon_has_passed_on_closed_bars():
    with connect() as con:
        seed(con, noisy_uptrend(60))
        early = issue(con, "shadow_view", "BTC", START + timedelta(days=58), direction="up", horizon_days=7, confidence=0.5)
        ready = issue(con, "shadow_view", "BTC", START + timedelta(days=30), direction="up", horizon_days=7, confidence=0.5)
    out = scoring.score()
    assert out["views_resolved"] == 1 and out["pending"] == 1
    with connect() as con:
        assert outcome(con, early) is None
        h, ret, hit = outcome(con, ready)
    assert h == 7 and ret > 0.05 and hit is True


def test_up_down_and_flat_are_judged_by_their_own_rules():
    with connect() as con:
        seed(con, noisy_uptrend(60))
        up = issue(con, "shadow_view", "BTC", START + timedelta(days=30), direction="up", horizon_days=3, confidence=0.5)
        down = issue(con, "shadow_view", "BTC", START + timedelta(days=30), direction="down", horizon_days=3, confidence=0.5)
        flat = issue(con, "shadow_view", "BTC", START + timedelta(days=30), direction="flat", horizon_days=3, confidence=0.5)
    scoring.score()
    with connect() as con:
        assert outcome(con, up)[2] is True and outcome(con, down)[2] is False and outcome(con, flat)[2] is False   # +3% is not 'flat'


def test_scoring_twice_does_not_duplicate_or_change_outcomes():
    with connect() as con:
        seed(con, noisy_uptrend(60))
        issue(con, "shadow_view", "BTC", START + timedelta(days=30), direction="up", horizon_days=3, confidence=0.5)
    scoring.score()
    second = scoring.score()
    assert second["views_resolved"] == 0
    with connect() as con:
        assert con.execute("SELECT count(*) FROM insight_outcomes").fetchone()[0] == 1


def test_a_flag_is_followed_by_a_large_move_only_when_the_move_is_large_relative_to_volatility():
    closes = noisy_uptrend(60, drift=0.001)
    closes[41:] = [c * 0.88 for c in closes[41:]]            # a -12% drop on day 41
    calm = noisy_uptrend(60, drift=0.001, seed=1)
    with connect() as con:
        seed(con, closes)
        seed(con, calm, symbol="ETHUSDT")
        hit = issue(con, "risk_flag", "BTC", START + timedelta(days=40), flag="volatility_spike", severity="high", reason="r")
        miss = issue(con, "risk_flag", "ETH", START + timedelta(days=40), flag="volatility_spike", severity="high", reason="r")
    scoring.score()
    with connect() as con:
        assert outcome(con, hit)[2] is True and outcome(con, miss)[2] is False


def test_assets_without_bars_are_left_alone_rather_than_guessed():
    with connect() as con:
        seed(con, noisy_uptrend(60))
        gold = issue(con, "risk_flag", "GOLD", START + timedelta(days=30), flag="macro_event", severity="medium", reason="r")
    out = scoring.score()
    assert out["flags_resolved"] == 0
    with connect() as con:
        assert outcome(con, gold) is None


def test_the_scorecard_reports_counts_next_to_rates():
    with connect() as con:
        seed(con, noisy_uptrend(60))
        issue(con, "shadow_view", "BTC", START + timedelta(days=30), direction="up", horizon_days=3, confidence=0.5)
        issue(con, "shadow_view", "BTC", START + timedelta(days=31), direction="down", horizon_days=3, confidence=0.5)
    scoring.score()
    with connect() as con:
        card = scoring.scorecard(con)
    assert card["views"] == 2 and card["view_hit_rate"] == pytest.approx(0.5) and card["flags"] == 0


def test_the_scorecard_separates_results_by_source():
    with connect() as con:
        seed(con, noisy_uptrend(60))
        issue(con, "shadow_view", "BTC", START + timedelta(days=30), direction="up", horizon_days=3, confidence=0.5)            # no source: a briefing
        issue(con, "shadow_view", "BTC", START + timedelta(days=31), direction="down", horizon_days=3, confidence=0.5, source="investigator")
    scoring.score()
    with connect() as con:
        card = scoring.scorecard(con)
    assert set(card["by_source"]) == {"briefing", "investigator"}
    assert card["by_source"]["briefing"]["views"] == 1 and card["by_source"]["investigator"]["views"] == 1
    assert card["by_source"]["briefing"]["view_hit_rate"] == 1.0 and card["by_source"]["investigator"]["view_hit_rate"] == 0.0
