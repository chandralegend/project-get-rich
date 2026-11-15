import json
from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from getrich import config
from getrich.agents import desk, trader, trader_scoring
from getrich.llm.client import ClaudeLLM
from getrich.obs.events import utcnow
from getrich.store.db import connect
from getrich.store.ledger import record_insight, verify_chain
from getrich.trading import book, limits as L

LIMITS_TOML = 'profile = "moderate"\nmax_exposure_fraction = 0.5\naccount_drawdown_halt = 0.3\ndaily_loss_halt = 0.055\nrisk_per_trade = 0.02\n'


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "config").mkdir(parents=True)
    (h / "config" / "limits.toml").write_text(LIMITS_TOML)
    monkeypatch.setenv("GETRICH_HOME", str(h))
    L.pin()
    return h


def seed(days=400, hours=400, seed_=0):
    rng = np.random.default_rng(seed_)
    now = utcnow()
    end_day = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    with connect() as con:
        for sym, base in (("BTCUSDT", 60000.0), ("ETHUSDT", 2000.0)):
            d = base * np.cumprod(1 + rng.normal(0.0005, 0.02, days))
            con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            [("binance", sym, "1d", end_day - timedelta(days=days - 1 - i), p, p * 1.01, p * 0.99, p, 100.0, 1.0, 1, now) for i, p in enumerate(d)])
            h = base * np.cumprod(1 + rng.normal(0.0, 0.004, hours))
            con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            [("binance", sym, "1h", end_hour - timedelta(hours=hours - 1 - i), p, p * 1.002, p * 0.998, p, 10.0, 1.0, 1, now) for i, p in enumerate(h)])


def seed_event(item_id="n_evt1", injection=False):
    with connect() as con:
        con.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?)", [item_id, "fed.press", "https://x", "t", "", None, utcnow() - timedelta(minutes=30), item_id + "h"])
        record_insight(con, asset="BTC", evidence=[item_id], model="claude-haiku-5-5", as_of=utcnow(), payload={
            "kind": "event_extraction", "source": "fed.press", "title": "t", "assets": ["BTC"], "event_type": "regulation", "direction": "risk_on", "horizon": "1-5d",
            "magnitude": "medium", "confidence": 0.6, "summary": "A licensing framework was published.", "injection_flag": injection, "heuristic_flags": []})


def idea(**over):
    base = {"asset": "BTC", "action": "open_long", "setup": "pullback", "conviction": 0.45, "thesis": "Pullback into the 24h range low inside an uptrend.", "invalidation": "A close below the 7d low.",
            "stop_pct": 0.02, "target_pct": 0.05, "max_hold_hours": 36, "risk_fraction": 0.01, "reduce_fraction": 0.0, "evidence": []}
    base.update(over)
    return base


def plan(ideas=None, **over):
    data = {"assessment": {"regime": "choppy", "narrative": "Range-bound with falling volume.", "main_risks": ["No event calendar"], "edge_check": "Small edge at best; a pullback with defined risk."},
            "stance": {"risk_posture": "neutral", "cash_target_fraction": 0.7, "reason": "Unproven inputs."}, "ideas": [idea()] if ideas is None else ideas,
            "watchlist": ["24h low"], "review_of_past_calls": "No previous calls."}
    data.update(over)
    return data


def response(data):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(data))], usage=SimpleNamespace(input_tokens=6000, output_tokens=1800), stop_reason="end_turn", _request_id="req_t")


class FakeSDK:
    def __init__(self, *responses):
        self.calls, self._q, self.messages = [], list(responses), self

    def create(self, **kw):
        self.calls.append(kw)
        return self._q.pop(0)


def run(data, **kw):
    sdk = FakeSDK(response(data))
    return trader.run(ClaudeLLM(sdk), **kw), sdk


# ------------------------------------------------------------------ the desk packet


def test_the_packet_carries_markets_signals_news_portfolio_limits_and_the_honest_track_record(home):
    seed()
    seed_event()
    p = desk.build_packet()
    for a in ("BTC", "ETH"):
        assert {"daily", "hourly", "forecasts"} <= set(p["markets"][a])
        assert p["markets"][a]["hourly"]["state_facts"]["ema12_above_ema48"] in (True, False)
    assert p["cross_asset"]["correlation_30d"] is not None
    assert p["portfolio"]["limits"]["risk_per_trade"] == 0.02 and p["portfolio"]["gate_facts"]["round_trip_cost_pct"] == 0.3
    assert "forecasters (Kronos, Chronos-2, TimesFM)" in p["signal_track_record"] and "calendar" in p["news"]
    assert p["news"]["events_24h"][0]["ref"] == "n_evt1"


def test_suspicious_events_never_reach_the_packet(home):
    seed()
    seed_event("n_bad", injection=True)
    p = desk.build_packet()
    assert p["news"]["events_24h"] == [] and p["news"]["withheld_as_suspicious"] == 1


def test_only_closed_hourly_bars_are_used(home):
    seed()
    now = utcnow()
    partial = now.replace(minute=0, second=0, microsecond=0)
    with connect() as con:
        con.execute("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ["binance", "BTCUSDT", "1h", partial, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1, now])
    p = desk.build_packet(now)
    assert p["markets"]["BTC"]["hourly"]["price"] > 1000


def test_dry_run_builds_the_packet_estimates_cost_and_calls_nothing(home):
    seed()
    sdk = FakeSDK()
    out = trader.run(ClaudeLLM(sdk), dry_run=True)
    assert out["status"] == "dry_run" and out["estimated_cost_usd"] > 0 and sdk.calls == []


# ------------------------------------------------------------------ validation and reconciliation


@pytest.mark.parametrize("over,fragment", [
    ({"stop_pct": 0.001}, "stop_pct"), ({"conviction": 1.5}, "conviction"), ({"risk_fraction": 0.0}, "risk_fraction"), ({"max_hold_hours": 0}, "max_hold_hours"),
    ({"thesis": ""}, "thesis"), ({"action": "buy_everything"}, "not allowed"), ({"target_pct": 3}, "target_pct")])
def test_validation_rejects_bad_ideas(over, fragment):
    errs = trader.validate_plan(plan([idea(**over)]), set())
    assert any(fragment in e for e in errs)


def test_validation_limits_ideas_and_one_idea_per_asset():
    assert any("more than one idea" in e for e in trader.validate_plan(plan([idea(), idea()]), set()))
    assert any("at most" in e for e in trader.validate_plan(plan([idea(asset="BTC")] * 5), set()))
    assert trader.validate_plan(plan(), set()) == []


def test_reconcile_drops_inconsistent_actions_and_strips_unshown_evidence():
    packet = {"portfolio": {"positions": [{"symbol": "ETHUSDT"}]}}
    kept, notes = trader.reconcile([idea(asset="BTC", action="exit"), idea(asset="ETH", action="open_long"), idea(asset="ETH", action="hold", evidence=["n_evt1", "n_fake"])],
                                   packet, {"n_evt1", "n_pkt"}, "n_pkt")
    assert [i["action"] for i in kept] == ["hold"]
    assert kept[0]["evidence"] == ["n_evt1", "n_pkt"] and len(notes) == 3


# ------------------------------------------------------------------ the full run


def test_a_run_records_plan_and_ideas_in_the_chain_stores_the_packet_and_makes_no_orders(home):
    seed()
    seed_event()
    out, sdk = run(plan([idea(evidence=["n_evt1"]), idea(asset="ETH", action="wait", setup="no_setup", stop_pct=0, target_pct=0, max_hold_hours=0, risk_fraction=0.0, thesis="No edge.", invalidation="n/a")]))
    assert out["status"] == "recorded" and out["ideas"] == 2 and out["proposals"] == []
    assert sdk.calls[0]["output_config"]["effort"] == "high" and "packet_ref" in sdk.calls[0]["messages"][0]["content"]
    with connect() as con:
        assert verify_chain(con)[0]
        kinds = [json.loads(r[0])["kind"] for r in con.execute("SELECT payload FROM insights ORDER BY seq").fetchall()]
        assert kinds.count("trader_plan") == 1 and kinds.count("trade_idea") == 2
        pkt = con.execute("SELECT summary FROM news_items WHERE source = 'desk_packet'").fetchone()[0]
        assert json.loads(pkt)["portfolio"]["limits"]["profile"] == "moderate"
        assert con.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
    text = open(out["path"]).read()
    assert "Gate what-if: **approved**" in text and "Edge check" in text


def test_the_gate_what_if_is_in_the_ledger_and_the_gate_can_only_shrink_the_request(home):
    seed()
    out, _ = run(plan([idea(risk_fraction=0.05, stop_pct=0.02)]))                  # asks for 5% risk; the limit is 2%
    with connect() as con:
        p = json.loads(con.execute("SELECT payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'trade_idea'").fetchone()[0])
    v = p["gate_whatif"]
    assert v["approved"] and v["risk_fraction"] <= 0.02 + 1e-9


def test_propose_creates_a_gate_checked_proposal_only_for_tradable_ideas(home):
    seed()
    out, _ = run(plan([idea(), idea(asset="ETH", action="open_short", setup="range_fade")]), propose=True)
    assert len(out["proposals"]) == 1 and out["proposals"][0]["asset"] == "BTC" and out["proposals"][0]["approved_by_gate"]
    orders = book.list_orders(10, "paper")
    assert len(orders) == 1 and orders[0]["status"] == "proposed" and orders[0]["source"] == "trader_agent"      # nobody approved it


def test_a_refusal_by_the_gate_is_reported_not_forced(home):
    seed()
    out, _ = run(plan([idea(stop_pct=0.006, target_pct=0.02)]), propose=True)                  # a stop the cost gate refuses
    assert out["proposals"][0]["approved_by_gate"] is False and any("cost_gate" in r for r in out["proposals"][0]["reasons"])


def test_a_bad_model_answer_stores_nothing(home):
    seed()
    out, _ = run(plan([idea(stop_pct=0.0001)]))
    assert out["status"] == "failed"
    with connect() as con:
        assert con.execute("SELECT count(*) FROM insights").fetchone()[0] == 0


def test_the_budget_cap_stops_the_call_before_it_is_made(home, monkeypatch):
    seed()
    monkeypatch.setenv("GETRICH_CLAUDE_MONTHLY_CAP_USD", "0.001")
    sdk = FakeSDK()
    out = trader.run(ClaudeLLM(sdk))
    assert out["status"] == "skipped" and sdk.calls == []


# ------------------------------------------------------------------ forward scoring


def hourly(rows):
    idx = pd.date_range("2024-01-01 01:00", periods=len(rows), freq="h", tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def sim(action="open_long", stop=0.02, tp=0.04, hold=10, price=100.0):
    return {"action": action, "price_at_issue": price, "stop_pct": stop, "target_pct": tp, "max_hold_hours": hold, "issue_bar_open": "2024-01-01 00:00"}


def test_a_long_hits_its_target_with_costs_taken_off():
    bars = hourly([(100, 101, 99.5, 100.5), (100.5, 104.5, 100, 104)] + [(104, 104, 104, 104)] * 8)
    r = trader_scoring.simulate(sim(), bars)
    assert r["kind"] == "take_profit" and r["bars"] == 2 and 0.03 < r["net"] < 0.04 and r["r"] > 1.5


def test_a_gap_through_the_stop_fills_at_the_worse_open_and_the_stop_wins_a_tie():
    gap = trader_scoring.simulate(sim(), hourly([(95, 96, 94, 95)] + [(95, 95, 95, 95)] * 9))
    assert gap["kind"] == "stop" and gap["r"] < -2
    tie = trader_scoring.simulate(sim(), hourly([(100, 105, 97, 100)] + [(100, 100, 100, 100)] * 9))
    assert tie["kind"] == "stop"


def test_a_short_wins_when_price_falls_and_an_idea_without_enough_bars_is_pending():
    r = trader_scoring.simulate(sim("open_short"), hourly([(100, 100.5, 95, 96)] + [(96, 96, 96, 96)] * 9))
    assert r["kind"] == "take_profit" and r["net"] > 0
    assert trader_scoring.simulate(sim(), hourly([(100, 100.5, 99.5, 100)] * 4)) is None
    assert trader_scoring.simulate(sim(hold=3), hourly([(100, 100.5, 99.5, 100)] * 4))["kind"] == "timeout"


def test_resolved_ideas_become_outcomes_a_scorecard_and_the_next_journal(home):
    seed()
    out, _ = run(plan([idea(stop_pct=0.02, target_pct=0.0, max_hold_hours=1)]))
    assert trader_scoring.score_ideas()["pending"] == 1                              # no bar has closed after the issue bar yet
    with connect() as con:
        issue = json.loads(con.execute("SELECT payload FROM insights WHERE json_extract_string(payload, '$.kind') = 'trade_idea'").fetchone()[0])
        t = pd.Timestamp(issue["issue_bar_open"], tz="UTC") + pd.Timedelta(hours=1)
        con.execute("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ["binance", "BTCUSDT", "1h", t.to_pydatetime(), issue["price_at_issue"], issue["price_at_issue"] * 1.01,
                                                                                  issue["price_at_issue"] * 0.999, issue["price_at_issue"] * 1.008, 1.0, 1.0, 1, utcnow()])
    assert trader_scoring.score_ideas()["resolved"] == 1
    j = trader_scoring.journal()
    assert j["record"]["resolved"]["n"] == 1 and j["recent_decisions"][0]["outcome"]["exit"] == "timeout"
    assert "pullback" in j["record"]["by_setup"]
    packet = desk.build_packet(utcnow(), j)
    assert packet["journal"]["record"]["resolved"]["n"] == 1
