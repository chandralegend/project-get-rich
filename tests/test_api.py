import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from getrich.api import jobs, views
from getrich.api.app import create_app
from getrich.obs.events import utcnow
from getrich.store.db import connect
from getrich.trading import book, limits as L

import test_trader as tt   # reuse the seeding helpers

ACT = {"X-Getrich-Action": "1"}


@pytest.fixture
def client(tt_home):
    views.clear_cache()
    return TestClient(create_app())


@pytest.fixture
def tt_home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "config").mkdir(parents=True)
    (h / "config" / "limits.toml").write_text(tt.LIMITS_TOML)
    (h / "docs").mkdir()
    (h / "docs" / "phase9-demo.md").write_text("# Demo study\n\nstuff\n\n**Verdict: X2 NOT SHOWN.**\n")
    (h / "docs" / "trials.json").write_text(json.dumps([{"phase": 1, "name": "a", "sharpe_annual": 0.5, "source": "x"}]))
    (h / "research").mkdir()
    monkeypatch.setenv("GETRICH_HOME", str(h))
    L.pin()
    tt.seed()
    return h


def test_the_read_views_answer_with_real_shapes(client):
    ov = client.get("/api/overview").json()
    assert ov["portfolio"]["equity"] == 500.0 and "limits" in ov["portfolio"] and ov["budget"]["cap"] == 30.0
    uni = client.get("/api/universe").json()
    assert {r["symbol"] for r in uni["rows"]} >= {"BTCUSDT", "ETHUSDT"} and "GBPUSD" in uni["no_data_yet"]
    b = client.get("/api/bars/BTCUSDT?timeframe=1h&limit=50").json()
    assert len(b["bars"]) == 50 and b["bars"][0]["t"] < b["bars"][-1]["t"]
    assert client.get("/api/instrument/BTCUSDT").json()["hourly"]["price"] > 0
    assert client.get("/api/orders").json()["limits"]["pinned"] is True
    h = client.get("/api/health").json()
    assert h["ledger"]["ok"] is True and "services" in h and h["budget"]["cap"] == 30.0
    r = client.get("/api/research").json()
    assert r["docs"][0]["verdict"].startswith("Verdict") and r["trials"]["count"] == 1
    assert "NOT SHOWN" in client.get("/api/docs/docs/phase9-demo.md").text


def test_unknown_things_are_404_and_bad_input_is_400(client):
    assert client.get("/api/bars/NOPE").status_code == 404
    assert client.get("/api/bars/BTCUSDT?timeframe=5m").status_code == 400
    assert client.get("/api/docs/docs/..%2Fsecret.md").status_code in (404, 400)
    assert client.get("/api/docs/other/x.md").status_code == 404
    assert client.get("/api/jobs/j_nope").status_code == 404


def test_state_changing_requests_need_the_action_header_and_a_local_origin(client):
    assert client.post("/api/risk/unhalt").status_code == 403
    assert client.post("/api/risk/unhalt", headers={**ACT, "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/risk/unhalt", headers={**ACT, "Origin": "http://localhost:8420"}).status_code == 200
    assert client.get("/api/overview", headers={"Origin": "https://evil.example"}).status_code == 200      # reads stay open on localhost


def test_a_trader_idea_becomes_a_gate_checked_proposal_the_owner_then_approves_or_rejects(client):
    from getrich.agents import trader
    from getrich.llm.client import ClaudeLLM
    sdk = tt.FakeSDK(tt.response(tt.plan([tt.idea(), tt.idea(instrument="ETHUSDT", action="open_short", setup="range_fade")])))
    trader.run(ClaudeLLM(sdk))
    plans = client.get("/api/trader/plans").json()
    ideas = plans["plans"][0]["ideas"]
    long_, short_ = next(i for i in ideas if i["action"] == "open_long"), next(i for i in ideas if i["action"] == "open_short")
    assert long_["gate_whatif"]["approved"] and short_["tradable"] is False
    assert client.post(f"/api/ideas/{short_['insight_id']}/propose", headers=ACT).status_code == 400          # a short can never become an order
    res = client.post(f"/api/ideas/{long_['insight_id']}/propose", headers=ACT).json()
    assert res["verdict"]["approved"] and book.list_orders(5, "paper")[0]["status"] == "proposed"
    oid = res["order_id"]
    assert client.get("/api/orders").json()["orders"][0]["order_id"] == oid
    assert client.post(f"/api/orders/{oid}/reject", headers=ACT).json()["ok"] is True
    res2 = client.post(f"/api/ideas/{long_['insight_id']}/propose", headers=ACT).json()
    done = client.post(f"/api/orders/{res2['order_id']}/approve", headers=ACT).json()
    assert done["ok"] is True
    assert client.get("/api/overview").json()["portfolio"]["positions"][0]["symbol"] == "BTCUSDT"


def test_an_old_idea_cannot_be_proposed(client):
    from getrich.agents import trader
    from getrich.llm.client import ClaudeLLM
    trader.run(ClaudeLLM(tt.FakeSDK(tt.response(tt.plan()))))
    iid = client.get("/api/trader/plans").json()["plans"][0]["ideas"][0]["insight_id"]
    with connect() as con:
        con.execute("UPDATE insights SET as_of = ? WHERE insight_id = ?", [utcnow() - timedelta(hours=3), iid])
    assert client.post(f"/api/ideas/{iid}/propose", headers=ACT).status_code == 409


def test_kill_flattens_and_blocks_until_lifted(client):
    assert client.post("/api/risk/kill", headers=ACT).json()["flattened"] == []
    assert client.get("/api/orders").json()["killed"] is True
    assert client.post("/api/risk/unkill", headers=ACT).json()["was_on"] is True
    assert client.get("/api/orders").json()["killed"] is False


def test_the_trader_can_only_be_started_in_shadow_mode_and_needs_a_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert client.post("/api/trader/run", headers=ACT, json={"classes": ["crypto"]}).status_code == 400
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert client.post("/api/trader/run", headers=ACT, json={"classes": ["bonds"]}).status_code == 400
    started = {}

    def fake_start(kind, args):
        started.update(kind=kind, args=args)
        return {"id": "j_x", "kind": kind, "status": "running"}
    monkeypatch.setattr(jobs, "start", fake_start)
    assert client.post("/api/trader/run", headers=ACT, json={"classes": ["crypto"]}).status_code == 200
    assert started == {"kind": "trader", "args": ["--classes", "crypto"]} and "--propose" not in started["args"]


def test_jobs_run_one_at_a_time_and_record_their_exit(tt_home):
    j = jobs.start("refresh-data", ["--help"])
    with pytest.raises(RuntimeError):
        jobs.start("refresh-data", ["--help"])
    import time
    for _ in range(100):
        if jobs.get(j["id"])["status"] != "running":
            break
        time.sleep(0.1)
    assert jobs.get(j["id"])["status"] == "done" and jobs.get(j["id"])["exit_code"] == 0
    with pytest.raises(ValueError):
        jobs.start("rm-rf", [])
