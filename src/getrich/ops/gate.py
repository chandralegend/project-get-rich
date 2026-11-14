"""`getrich gate`: evaluates the Phase 0 exit gate from evidence in the event log and the store.

Gate (ARCHITECTURE.md section 6): the recorder runs a week unattended, data is reproducible, and
killing a process raises an alert. Thresholds below are suggested starting points, not research findings.

Statuses: PASS, FAIL, PENDING (not yet true, will become true with time or an action), MANUAL (only you
can confirm it; record it with `getrich ack <item>`), WARN (passes, but look at it).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from .. import config
from ..obs.events import emit, utcnow
from ..store.ledger import verify_chain
from . import doctor
from .watchdog import EXPECTED_MAX_AGE

# When the launchd jobs were first installed from the final location. The week is counted from here.
DEFAULT_SINCE = datetime(2026, 11, 14, 9, 41, tzinfo=timezone.utc)
WINDOW_DAYS = 7
WATCHDOG_MIN_COVERAGE = 0.99  # fraction of minutes with a watchdog heartbeat
WATCHDOG_MAX_GAP = timedelta(minutes=15)
FAULT_ALERT_WITHIN = timedelta(minutes=5)
ACK_ITEMS = {
    "update-reboots-off": "automatic macOS update reboots are turned off",
    "notification-seen": "a macOS notification titled 'getrich P1' appeared during the kill test",
}
BENCH_CASES = 7


@dataclass
class Result:
    name: str
    status: str
    detail: str


def _max_gap(stamps: list[datetime], start: datetime, end: datetime) -> timedelta:
    points = [start] + sorted(s for s in stamps if start <= s <= end) + [end]
    return max((b - a for a, b in zip(points, points[1:])), default=timedelta(0))


def _events(con, names: list[str], since: datetime, service: str | None = None):
    q = "SELECT ts, event, service, data FROM events WHERE ts >= ? AND event IN ({})".format(",".join("?" * len(names)))
    args: list = [since, *names]
    if service:
        q += " AND service = ?"
        args.append(service)
    return con.execute(q + " ORDER BY ts", args).fetchall()


def evaluate(con: duckdb.DuckDBPyConnection, since: datetime, now: datetime, host_checks: bool = True) -> list[Result]:
    out: list[Result] = []
    elapsed = now - since

    # 1. time
    days = elapsed.total_seconds() / 86400
    out.append(Result("one-week window", "PASS" if days >= WINDOW_DAYS else "PENDING",
                      f"{days:.1f} of {WINDOW_DAYS} days since {since:%Y-%m-%d %H:%M} UTC"))

    # 2. collectors ran successfully with no long gaps
    for svc, limit in EXPECTED_MAX_AGE.items():
        runs = [ts for ts, _, _, data in _events(con, ["collector.run"], since, svc) if json.loads(data).get("ok") is True]
        if not runs:
            out.append(Result(f"{svc} runs", "FAIL", "no successful run recorded"))
            continue
        gap = _max_gap(runs, since, now)
        ok = gap <= timedelta(seconds=limit)
        out.append(Result(f"{svc} runs", "PASS" if ok else "FAIL",
                          f"{len(runs)} successful runs, longest gap {gap.total_seconds() / 3600:.1f}h (limit {limit / 3600:.0f}h)"))

    # 3. watchdog continuity
    beats = [ts for ts, _, _, _ in _events(con, ["service.heartbeat"], since, "watchdog")]
    minutes = max(int(elapsed.total_seconds() // 60), 1)
    covered = len({int(b.timestamp() // 60) for b in beats})
    coverage = min(covered / minutes, 1.0)
    gap = _max_gap(beats, since, now)
    ok = coverage >= WATCHDOG_MIN_COVERAGE and gap <= WATCHDOG_MAX_GAP
    out.append(Result("watchdog continuity", "PASS" if ok else "FAIL",
                      f"{coverage:.1%} of minutes covered, longest gap {gap.total_seconds() / 60:.0f} min "
                      f"(need {WATCHDOG_MIN_COVERAGE:.0%} and under {WATCHDOG_MAX_GAP.total_seconds() / 60:.0f} min)"))

    # 4. fault injection: injected -> alert raised -> alert cleared
    marks = _events(con, ["test.fault_injected"], since)
    raised_all = _events(con, ["alert.raised"], since)
    cleared_all = _events(con, ["alert.cleared"], since)
    proven = None
    for ts, *_ in marks:
        raised = next((r for r in raised_all if ts <= r[0] <= ts + FAULT_ALERT_WITHIN), None)
        if raised and any(c[0] > raised[0] and json.loads(c[3]).get("key") == json.loads(raised[3]).get("key") for c in cleared_all):
            proven = (ts, raised[0])
            break
    out.append(Result("fault -> alert -> recovery", "PASS" if proven else "FAIL",
                      f"injected {proven[0].astimezone(timezone.utc):%Y-%m-%d %H:%M:%S} UTC, alert after "
                      f"{(proven[1] - proven[0]).total_seconds():.0f}s, then cleared"
                      if proven else "no complete injected-fault sequence in the log (run the kill test)"))

    # 5. unplanned alerts (alerts within 10 minutes after an injected fault do not count)
    test_windows = [(ts, ts + timedelta(minutes=10)) for ts, *_ in marks]
    real = [(ts, json.loads(data)) for ts, _, _, data in raised_all if not any(a <= ts <= b for a, b in test_windows)]
    p0 = [d for _, d in real if d.get("severity") == "P0"]
    p1 = [d for _, d in real if d.get("severity") == "P1"]
    status = "FAIL" if p0 else "WARN" if p1 else "PASS"
    out.append(Result("unplanned alerts", status, f"{len(p0)} P0, {len(p1)} P1" + (f": {p1[0].get('message')}" if p1 and not p0 else "")))

    # 6. data integrity
    rows = con.execute(
        "SELECT symbol, count(*), min(ts_open), max(ts_open) FROM bars WHERE venue='binance' AND timeframe='1d' GROUP BY symbol"
    ).fetchall()
    if not rows:
        out.append(Result("daily bars complete", "FAIL", "no daily bars stored"))
    else:
        bad = []
        for symbol, n, lo, hi in rows:
            lo_d, hi_d = lo.astimezone(timezone.utc).date(), hi.astimezone(timezone.utc).date()
            expected = (hi_d - lo_d).days + 1
            if n != expected or hi_d < (now - timedelta(days=2)).astimezone(timezone.utc).date():
                bad.append(f"{symbol}: {n} bars, expected {expected}, latest {hi_d:%Y-%m-%d}")
        out.append(Result("daily bars complete", "FAIL" if bad else "PASS",
                          "; ".join(bad) if bad else f"{len(rows)} symbols, no missing days, up to date"))

    # 7. insight ledger
    chain_ok, n, bad_seq = verify_chain(con)
    out.append(Result("insight ledger chain", "PASS" if chain_ok else "FAIL",
                      f"{n} insights, chain intact" if chain_ok else f"broken at seq {bad_seq}"))

    # 8. external heartbeat
    import os

    if not os.environ.get("GETRICH_HEARTBEAT_URL"):
        out.append(Result("external heartbeat", "PENDING", "not configured: create the check, put its URL in .env (docs/phase0-checklist.md)"))
    else:
        pings = _events(con, ["watchdog.pinged"], now - timedelta(minutes=10))
        out.append(Result("external heartbeat", "PASS" if pings else "FAIL",
                          f"{len(pings)} successful pings in the last 10 minutes" if pings else "URL set but no successful ping in 10 minutes"))

    # 9. host settings and manual attestations
    if host_checks:
        host = {name: (st, detail) for st, name, detail in doctor.run()}
        st, detail = host["system sleep"]
        out.append(Result("Mac does not sleep", "PASS" if st == "OK" else "FAIL", detail))
        st, detail = host["restart after power loss"]
        out.append(Result("restart after power loss", "PASS" if st == "OK" else "PENDING", "on" if st == "OK" else detail))
        st, detail = host["libomp (LightGBM)"]
        out.append(Result("libomp installed", "PASS" if st == "OK" else "FAIL", detail))
    acks = {json.loads(d).get("item"): ts for ts, _, _, d in _events(con, ["manual.ack"], datetime(2000, 1, 1, tzinfo=timezone.utc))}
    for item, text in ACK_ITEMS.items():
        out.append(Result(f"you confirmed: {item}", "PASS" if item in acks else "MANUAL",
                          f"attested {acks[item].astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC (not machine-verified)" if item in acks
                          else f"only you can confirm that {text}; then run `getrich ack {item}`"))

    # 10. compute benchmark
    bench = sorted(Path(config.root(), "docs", "benchmarks").glob("*.json"))
    if bench:
        data = json.loads(bench[-1].read_text())
        clean = [x for x in data if "error" not in x and "skipped" not in x]
        out.append(Result("compute benchmark", "PASS" if len(clean) >= BENCH_CASES else "FAIL",
                          f"{len(clean)} of {BENCH_CASES} cases recorded in {bench[-1].name}"))
    else:
        out.append(Result("compute benchmark", "FAIL", "no results file in docs/benchmarks"))
    return out


def overall(results: list[Result]) -> str:
    if any(r.status == "FAIL" for r in results):
        return "FAIL"
    if any(r.status in ("PENDING", "MANUAL") for r in results):
        return "NOT YET"
    return "PASS"


def record_ack(item: str, note: str = "") -> None:
    if item not in ACK_ITEMS:
        raise ValueError(f"unknown item {item!r}; choose one of: {', '.join(ACK_ITEMS)}")
    emit("manual.ack", service="operator", item=item, statement=ACK_ITEMS[item], note=note)
