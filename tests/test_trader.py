import json
from datetime import datetime, timedelta, timezone
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


def seed(days=400, hours=400, seed_=0, now=None):
    rng = np.random.default_rng(seed_)
    now = now or utcnow()
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


WED = datetime(2026, 11, 11, 12, 30, tzinfo=timezone.utc)      # a weekday midday: forex is open
SAT = datetime(2026, 11, 14, 12, 30, tzinfo=timezone.utc)      # the weekend: forex is closed


def seed_fx(now, sym="EURUSD", base=1.08, venue="yahoo", hours=400, days=400):
    rng = np.random.default_rng(5)
    end_day = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    with connect() as con:
        d = base * np.cumprod(1 + rng.normal(0.0, 0.004, days))
        con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(venue, sym, "1d", end_day - timedelta(days=days - 1 - i), p, p * 1.003, p * 0.997, p, 0.0, 0.0, 0, now) for i, p in enumerate(d)])
        h = base * np.cumprod(1 + rng.normal(0.0, 0.0008, hours))
        con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(venue, sym, "1h", end_hour - timedelta(hours=hours - 1 - i), p, p * 1.0004, p * 0.9996, p, 0.0, 0.0, 0, now) for i, p in enumerate(h)])


def seed_event(item_id="n_evt1", injection=False):
    with connect() as con:
        con.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?)", [item_id, "fed.press", "https://x", "t", "", None, utcnow() - timedelta(minutes=30), item_id + "h"])
        record_insight(con, asset="BTC", evidence=[item_id], model="claude-haiku-5-5", as_of=utcnow(), payload={
            "kind": "event_extraction", "source": "fed.press", "title": "t", "assets": ["BTC"], "event_type": "regulation", "direction": "risk_on", "horizon": "1-5d",
            "magnitude": "medium", "confidence": 0.6, "summary": "A licensing framework was published.", "injection_flag": injection, "heuristic_flags": []})


def idea(**over):
    base = {"instrument": "BTCUSDT", "action": "open_long", "setup": "pullback", "conviction": 0.45, "thesis": "Pullback into the 24h range low inside an uptrend.", "invalidation": "A close below the 7d low.",
            "stop_pct": 0.02, "target_pct": 0.05, "max_hold_hours": 36, "risk_fraction": 0.01, "reduce_fraction": 0.0, "evidence": []}
    base.update(over)
    return base


def plan(ideas=None, **over):
    data = {"assessment": {"regime": "choppy", "narrative": "Range-bound with falling volume.", "main_risks": ["No event calendar"], "edge_check": "Small edge at best; a pullback with defined risk."},
            "stance": {"risk_posture": "neutral", "cash_target_fraction": 0.7, "reason": "Unproven inputs."}, "universe_view": "Looked at BTC and ETH; nothing else has data.", "ideas": [idea()] if ideas is None else ideas,
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
    for a in ("BTCUSDT", "ETHUSDT"):
        assert {"daily", "hourly", "forecasts"} <= set(p["markets"][a])
        assert p["markets"][a]["hourly"]["state_facts"]["ema12_above_ema48"] in (True, False)
    assert p["cross_asset"]["btc_eth_correlation_30d"] is not None
    assert p["portfolio"]["limits"]["risk_per_trade"] == 0.02 and p["universe"]["instruments"]["BTCUSDT"]["round_trip_cost_pct"] == 0.3
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
    assert p["markets"]["BTCUSDT"]["hourly"]["price"] > 1000


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
    errs = trader.validate_plan(plan([idea(**over)]), set(), ["BTCUSDT", "ETHUSDT"])
    assert any(fragment in e for e in errs)


def test_validation_limits_ideas_and_one_idea_per_asset():
    assert any("more than one idea" in e for e in trader.validate_plan(plan([idea(), idea()]), set(), ["BTCUSDT"]))
    assert any("at most" in e for e in trader.validate_plan(plan([idea()] * 7), set(), ["BTCUSDT"]))
    assert trader.validate_plan(plan(), set(), ["BTCUSDT"]) == []
    assert any("not allowed" in e for e in trader.validate_plan(plan([idea(instrument="EURUSD")]), set(), ["BTCUSDT"]))     # an instrument without data cannot be chosen


def test_reconcile_drops_inconsistent_actions_and_strips_unshown_evidence():
    ok = {"available": True, "can_open_now": True}
    packet = {"portfolio": {"positions": [{"symbol": "ETHUSDT"}]}, "universe": {"instruments": {"BTCUSDT": ok, "ETHUSDT": ok}}}
    kept, notes = trader.reconcile([idea(instrument="BTCUSDT", action="exit"), idea(instrument="ETHUSDT", action="open_long"), idea(instrument="ETHUSDT", action="hold", evidence=["n_evt1", "n_fake"])],
                                   packet, {"n_evt1", "n_pkt"}, "n_pkt")
    assert [i["action"] for i in kept] == ["hold"]
    assert kept[0]["evidence"] == ["n_evt1", "n_pkt"] and len(notes) == 3


# ------------------------------------------------------------------ the full run


def test_a_run_records_plan_and_ideas_in_the_chain_stores_the_packet_and_makes_no_orders(home):
    seed()
    seed_event()
    out, sdk = run(plan([idea(evidence=["n_evt1"]), idea(instrument="ETHUSDT", action="wait", setup="no_setup", stop_pct=0, target_pct=0, max_hold_hours=0, risk_fraction=0.0, thesis="No edge.", invalidation="n/a")]))
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
    out, _ = run(plan([idea(), idea(instrument="ETHUSDT", action="open_short", setup="range_fade")]), propose=True)
    assert len(out["proposals"]) == 1 and out["proposals"][0]["instrument"] == "BTCUSDT" and out["proposals"][0]["approved_by_gate"]
    orders = book.list_orders(10, "paper")
    assert len(orders) == 1 and orders[0]["status"] == "proposed" and orders[0]["source"] == "trader_agent"      # nobody approved it


def test_a_refusal_by_the_gate_is_reported_not_forced(home):
    seed()
    book.kill_path().parent.mkdir(parents=True, exist_ok=True)
    book.kill_path().write_text("test\n")                                                       # the kill switch is on: no new positions
    out, _ = run(plan([idea()]), propose=True)
    assert out["proposals"][0]["approved_by_gate"] is False and any("kill_switch" in r for r in out["proposals"][0]["reasons"])


def test_a_stop_tighter_than_the_instruments_own_minimum_is_a_validation_failure(home):
    seed()
    out, _ = run(plan([idea(stop_pct=0.006)]))                                                   # BTC needs about 1.2% at 30 bps round trip
    assert out["status"] == "failed"


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


# ------------------------------------------------------------------ the wider universe: forex, gold, crypto alts


def seed_all(now):
    seed(now=now)
    seed_fx(now, "EURUSD", 1.08)
    seed_fx(now, "XAUUSD", 2600.0)
    seed_fx(now, "JPYUSD", 0.0065)
    seed_fx(now, "SOLUSDT", 150.0, venue="binance")


def test_the_universe_scan_has_a_row_per_instrument_with_hours_costs_and_minimum_stops(home):
    seed_all(WED)
    p = desk.build_packet(WED)
    u = p["universe"]["instruments"]
    assert {"BTCUSDT", "ETHUSDT", "EURUSD", "XAUUSD", "JPYUSD", "SOLUSDT"} <= set(u) and "GBPUSD" in p["universe"]["no_data_yet"]
    assert u["EURUSD"]["class"] == "fx" and u["EURUSD"]["can_open_now"] and u["EURUSD"]["round_trip_cost_pct"] < u["BTCUSDT"]["round_trip_cost_pct"]
    assert u["EURUSD"]["min_stop_pct"] < u["BTCUSDT"]["min_stop_pct"]                             # forex allows tighter stops than crypto
    assert u["JPYUSD"]["available"] and "dollar_vs_majors_5d" in p["cross_asset"]
    assert "forex and metals" in p["signal_track_record"]
    assert set(p["markets"]) >= {"BTCUSDT", "ETHUSDT"} and len(p["markets"]) <= 2 + desk.DETAIL_EXTRA


def test_forex_is_closed_on_the_weekend_in_the_scan_and_ideas_on_it_are_dropped(home):
    seed_all(SAT)
    p = desk.build_packet(SAT)
    row = p["universe"]["instruments"]["EURUSD"]
    assert row["market_open"] is False and row["can_open_now"] is False
    assert p["universe"]["instruments"]["BTCUSDT"]["can_open_now"] is True
    kept, notes = trader.reconcile([idea(instrument="EURUSD", stop_pct=0.003)], p, {"n_pkt"}, "n_pkt")
    assert kept == [] and "closed" in notes[0]


def test_the_agent_can_choose_forex_and_the_gate_sizes_it_with_its_own_rules_and_costs(home):
    seed_all(WED)
    row = desk.build_packet(WED)["universe"]["instruments"]["EURUSD"]
    assert row["can_open_now"]
    out, sdk = run_at(WED, plan([idea(instrument="EURUSD", setup="relative_strength", stop_pct=0.004, target_pct=0.01, risk_fraction=0.01),
                                 idea(instrument="BTCUSDT", action="wait", setup="no_setup", stop_pct=0, target_pct=0, max_hold_hours=0, risk_fraction=0.0, thesis="Nothing.", invalidation="n/a")]), propose=True)
    assert out["status"] == "recorded" and out["proposals"][0]["instrument"] == "EURUSD" and out["proposals"][0]["approved_by_gate"]
    schema = sdk.calls[0]["output_config"]["format"]["schema"]
    assert "EURUSD" in schema["properties"]["ideas"]["items"]["properties"]["instrument"]["enum"] and "GBPUSD" not in schema["properties"]["ideas"]["items"]["properties"]["instrument"]["enum"]
    order = book.list_orders(5, "paper")[0]
    assert order["symbol"] == "EURUSD" and order["source"] == "trader_agent"


def run_at(now, data, **kw):
    sdk = FakeSDK(response(data))
    return trader.run(ClaudeLLM(sdk), now=now, **kw), sdk


def test_forex_stops_under_the_instruments_minimum_are_refused_by_the_gate_too(home):
    from getrich.trading import gate
    from getrich.trading.types import OrderIntent
    seed_all(WED)
    state = book.load_state(["EURUSD"], WED)
    lim, _ = L.load()
    px = state.prices["EURUSD"][0]
    ok = gate.evaluate(OrderIntent("EURUSD", "buy", stop_price=px * (1 - 0.003), risk_fraction=0.01), state, lim)
    tight = gate.evaluate(OrderIntent("EURUSD", "buy", stop_price=px * (1 - 0.001), risk_fraction=0.01), state, lim)
    assert ok.approved and not tight.approved and any("stop_distance" in r for r in tight.reasons)
    sat = book.load_state(["EURUSD"], SAT)
    closed = gate.evaluate(OrderIntent("EURUSD", "buy", stop_price=px * (1 - 0.003)), sat, lim)
    assert not closed.approved and any("market_open" in r for r in closed.reasons)


def test_an_idea_on_forex_is_scored_with_forex_costs_not_crypto_costs():
    from getrich.eval.costs import CostModel
    bars = hourly([(1.0800, 1.0800, 1.0800, 1.0800)] + [(1.0800, 1.0800, 1.0800, 1.0800)] * 3)
    idea_ = {"action": "open_long", "price_at_issue": 1.0800, "stop_pct": 0.004, "target_pct": 0.0, "max_hold_hours": 3, "issue_bar_open": "2024-01-01 00:00"}
    fx = trader_scoring.simulate(idea_, bars, instruments_cost("EURUSD"))
    cr = trader_scoring.simulate(idea_, bars, CostModel())
    assert fx["net"] > cr["net"] and fx["net"] == pytest.approx(-2 * 1.0 / 1e4, abs=1e-5)


def instruments_cost(sym):
    from getrich.trading import instruments
    return instruments.cost_for(sym)


def test_old_plans_that_named_assets_btc_and_eth_still_score(home):
    seed()
    with connect() as con:
        con.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?)", ["n_old", "desk_packet", "desk://packet", "t", "{}", None, utcnow() - timedelta(hours=3), "hh"])
        record_insight(con, asset="BTC", evidence=["n_old"], model="claude-sonnet-5-5", as_of=utcnow(), payload={
            "kind": "trade_idea", "action": "open_long", "setup": "pullback", "conviction": 0.4, "thesis": "x", "stop_pct": 0.02, "target_pct": 0.0, "max_hold_hours": 1,
            "price_at_issue": 60000.0, "issue_bar_open": f"{utcnow() - timedelta(hours=6):%Y-%m-%d %H:%M}"})
    assert trader_scoring.score_ideas()["resolved"] == 1


def test_an_instrument_whose_hourly_feed_is_days_behind_is_unavailable_not_misleading(home):
    seed_all(WED)
    seed_fx(WED - timedelta(days=10), "GBPUSD", 1.27)                      # its newest hourly bar is ten days old
    p = desk.build_packet(WED)
    assert p["universe"]["instruments"]["GBPUSD"]["available"] is False and "old" in p["universe"]["instruments"]["GBPUSD"]["why"]
    assert p["universe"]["instruments"]["EURUSD"]["available"] is True
