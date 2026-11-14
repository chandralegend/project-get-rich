import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest

from getrich import config
from getrich.obs.ingest import ingest_events
from getrich.ops import gate
from getrich.store.db import connect

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=8)


def _iso(dt):
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write(rows):
    """rows: (datetime, event, service, data). Appends to the per-day event files."""
    by_day = defaultdict(list)
    for ts, event, service, data in rows:
        rec = {"ts": _iso(ts), "event": event, "service": service, "level": "info",
               "decision_id": None, "item_id": None, "data": data}
        by_day[ts.strftime("%Y-%m-%d")].append(json.dumps(rec))
    config.logs_dir().mkdir(parents=True, exist_ok=True)
    for day, lines in by_day.items():
        with open(config.logs_dir() / f"events-{day}.jsonl", "a") as f:
            f.write("\n".join(lines) + "\n")


def _scenario(skip_collector_hours=None, watchdog_gap_minutes=0, extra=()):
    rows = []
    hours = int((NOW - SINCE).total_seconds() // 3600)
    for h in range(1, hours + 1):
        ts = SINCE + timedelta(hours=h) - timedelta(minutes=5)
        for svc in ("collector.binance", "collector.news", "collector.webnews"):
            if svc == "collector.news" and skip_collector_hours and h in skip_collector_hours:
                continue
            rows.append((ts, "collector.run", svc, {"ok": True}))
    gap_start = SINCE + timedelta(days=3)
    minutes = int((NOW - SINCE).total_seconds() // 60)
    for m in range(1, minutes + 1):
        ts = SINCE + timedelta(minutes=m)
        if watchdog_gap_minutes and gap_start <= ts < gap_start + timedelta(minutes=watchdog_gap_minutes):
            continue
        rows.append((ts, "service.heartbeat", "watchdog", {"ok": True}))
    t = SINCE + timedelta(days=2)  # a complete kill test
    rows += [
        (t, "test.fault_injected", "killtest", {"target": "collector.news"}),
        (t + timedelta(seconds=50), "alert.raised", "watchdog", {"key": "stale:collector.news", "severity": "P1", "message": "m"}),
        (t + timedelta(seconds=110), "alert.cleared", "watchdog", {"key": "stale:collector.news"}),
    ]
    rows += list(extra)
    _write(rows)
    with connect() as con:
        con.execute(
            "INSERT INTO bars SELECT 'binance','BTCUSDT','1d', ts, 1,1,1,1,1,1,1, ts "
            "FROM generate_series(TIMESTAMPTZ '2026-10-01', TIMESTAMPTZ '2026-11-21', INTERVAL 1 DAY) t(ts)"
        )
        ingest_events(con)
        return {r.name: r for r in gate.evaluate(con, SINCE, NOW, host_checks=False)}


def test_healthy_week_passes_every_automatic_check_and_waits_on_the_humans(monkeypatch):
    monkeypatch.delenv("GETRICH_HEARTBEAT_URL", raising=False)
    res = _scenario()
    for name in ("one-week window", "collector.binance runs", "collector.news runs", "collector.webnews runs", "watchdog continuity",
                 "fault -> alert -> recovery", "unplanned alerts", "daily bars complete", "insight ledger chain"):
        assert res[name].status == "PASS", (name, res[name].detail)
    assert res["external heartbeat"].status == "PENDING"
    assert res["you confirmed: update-reboots-off"].status == "MANUAL"
    assert gate.overall(list(res.values())) == "NOT YET"


def test_everything_confirmed_gives_pass(monkeypatch):
    monkeypatch.setenv("GETRICH_HEARTBEAT_URL", "https://example.invalid/ping")
    extra = [(NOW - timedelta(minutes=2), "watchdog.pinged", "watchdog", {"status": 200})]
    extra += [(NOW - timedelta(days=1), "manual.ack", "operator", {"item": item}) for item in gate.ACK_ITEMS]
    res = _scenario(extra=extra)
    assert res["external heartbeat"].status == "PASS"
    assert all(r.status == "PASS" for r in res.values()), {k: v.status for k, v in res.items() if v.status != "PASS"}
    assert gate.overall(list(res.values())) == "PASS"


def test_a_five_hour_collector_gap_fails_the_gate():
    res = _scenario(skip_collector_hours=set(range(50, 56)))
    assert res["collector.news runs"].status == "FAIL"
    assert gate.overall(list(res.values())) == "FAIL"


def test_a_long_watchdog_outage_fails():
    res = _scenario(watchdog_gap_minutes=40)
    assert res["watchdog continuity"].status == "FAIL"


def test_unplanned_p0_fails_and_p1_warns():
    p0 = [(NOW - timedelta(days=4), "alert.raised", "watchdog", {"key": "disk_low", "severity": "P0", "message": "x"})]
    assert _scenario(extra=p0)["unplanned alerts"].status == "FAIL"


def test_unplanned_p1_is_a_warning():
    p1 = [(NOW - timedelta(days=4), "alert.raised", "watchdog", {"key": "stale:collector.news", "severity": "P1", "message": "x"})]
    assert _scenario(extra=p1)["unplanned alerts"].status == "WARN"


def test_no_kill_test_in_the_log_fails():
    with connect() as con:
        ingest_events(con)
        res = {r.name: r for r in gate.evaluate(con, SINCE, NOW, host_checks=False)}
    assert res["fault -> alert -> recovery"].status == "FAIL"


def test_unknown_ack_item_is_rejected():
    with pytest.raises(ValueError):
        gate.record_ack("not-a-thing")
