import json

from getrich import config
from getrich.obs.heartbeat import beat
from getrich.ops import watchdog


def _alerts(keys):
    return {a.key: a for a in keys}


def test_never_ran_is_a_p2_not_a_page():
    a = _alerts(watchdog.check())
    assert a["never_ran:collector.binance"].severity == "P2"


def test_healthy_collectors_raise_no_p0_or_p1():
    beat("collector.binance", ok=True)
    beat("collector.news", ok=True)
    assert not [a for a in watchdog.check() if a.severity in ("P0", "P1")]


def test_stale_collector_is_p1(monkeypatch):
    beat("collector.binance", ok=True)
    beat("collector.news", ok=True)
    monkeypatch.setitem(watchdog.EXPECTED_MAX_AGE, "collector.news", -1)  # anything is stale
    a = _alerts(watchdog.check())
    assert a["stale:collector.news"].severity == "P1"
    assert "stale:collector.binance" not in a


def test_failed_run_does_not_refresh_last_ok(monkeypatch):
    beat("collector.news", ok=False)  # never succeeded
    a = _alerts(watchdog.check())
    assert a["stale:collector.news"].severity == "P1"


def test_alert_lifecycle_raise_then_clear_and_ping_only_when_healthy(monkeypatch):
    pings = []
    monkeypatch.setattr(watchdog, "_ping", lambda: pings.append(1))
    monkeypatch.setitem(watchdog.EXPECTED_MAX_AGE, "collector.news", -1)
    beat("collector.binance", ok=True)
    beat("collector.news", ok=True)

    watchdog.run(notify=False)
    state = json.loads((config.state_dir() / "alerts.json").read_text())
    assert state["active"]["stale:collector.news"]["severity"] == "P1"
    assert pings == []  # a P1 is active: the dead-man's switch must NOT be pinged

    monkeypatch.setitem(watchdog.EXPECTED_MAX_AGE, "collector.news", 3 * 3600)
    watchdog.run(notify=False)
    state = json.loads((config.state_dir() / "alerts.json").read_text())
    assert "stale:collector.news" not in state["active"]
    assert pings == [1]  # healthy again: ping sent

    log = "".join(p.read_text() for p in config.logs_dir().glob("events-*.jsonl"))
    assert '"alert.raised"' in log and '"alert.cleared"' in log


def test_watchdog_writes_its_own_heartbeat():
    watchdog.run(notify=False, ping=False)
    from getrich.obs.heartbeat import read

    assert read("watchdog")["ok"] is True
