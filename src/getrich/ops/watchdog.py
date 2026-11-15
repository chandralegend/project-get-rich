"""Watchdog: a separate process that checks everything else and raises alerts.

Runs every minute under launchd. Alert delivery in Phase 0: the event log, a macOS notification for
P0/P1, and an optional external dead-man's-switch ping (GETRICH_HEARTBEAT_URL) that is sent ONLY when
no P0/P1 alert is active. If this process, or the whole Mac, stops, the pings stop and the external
service alerts you.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import timedelta

import httpx

from .. import config
from ..obs.events import emit, iso, parse_ts, utcnow
from ..obs.heartbeat import beat, read
from ..obs.ingest import ingest_events
from ..store.db import connect
from ..llm import budget
from ..store.ledger import verify_chain

SERVICE = "watchdog"
# Max seconds since the last SUCCESSFUL run before a service is considered stale (starting points).
EXPECTED_MAX_AGE = {"collector.binance": 3 * 3600, "collector.news": 3 * 3600, "collector.webnews": 4 * 3600}
RENOTIFY_SECONDS = {"P0": 3600, "P1": 6 * 3600}
DISK_P1_GIB, DISK_P0_GIB = 10.0, 5.0


@dataclass
class Alert:
    key: str
    severity: str  # P0 act now, P1 within the hour, P2 digest
    message: str
    action: str


def _fmt_age(seconds: float) -> str:
    return f"{seconds / 3600:.1f}h" if seconds >= 3600 else f"{seconds / 60:.0f}m"


def check(now=None) -> list[Alert]:
    now = now or utcnow()
    alerts: list[Alert] = []

    for svc, max_age in EXPECTED_MAX_AGE.items():
        hb = read(svc)
        cmd = svc.replace("collector.", "collect-")
        if hb is None:
            alerts.append(Alert(f"never_ran:{svc}", "P2", f"{svc} has never run", f"run `getrich {cmd}` once"))
            continue
        last_ok = hb.get("last_ok_ts")
        age = (now - parse_ts(last_ok)).total_seconds() if last_ok else None
        if age is None or age > max_age:
            alerts.append(
                Alert(
                    f"stale:{svc}",
                    "P1",
                    f"{svc} has not succeeded for {_fmt_age(age) if age is not None else 'ever'}",
                    f"run `getrich {cmd}` and read data/logs for collector.error events",
                )
            )

    config.ensure_dirs()
    free_gib = shutil.disk_usage(config.data_dir()).free / 2**30
    if free_gib < DISK_P0_GIB:
        alerts.append(Alert("disk_low", "P0", f"disk free {free_gib:.1f} GiB", "free space now; collectors will fail"))
    elif free_gib < DISK_P1_GIB:
        alerts.append(Alert("disk_low", "P1", f"disk free {free_gib:.1f} GiB", "free space or move data/ to an external drive"))

    try:
        with connect(timeout=5) as con:
            chain_ok, _, bad_seq = verify_chain(con)
            spent = budget.month_spend_con(con)
        if not chain_ok:
            alerts.append(
                Alert(
                    "ledger_broken", "P0", f"insight ledger hash chain is broken at seq {bad_seq}",
                    "stop trading; restore data/getrich.duckdb from backup and find out what changed it",
                )
            )
        cap = budget.monthly_cap()
        if spent >= cap:
            alerts.append(Alert("claude_budget_exhausted", "P1", f"Claude spend ${spent:.2f} reached the ${cap:.2f} monthly cap",
                                "agents are paused until next month; raise GETRICH_CLAUDE_MONTHLY_CAP_USD only deliberately"))
        elif spent >= budget.WARN_FRACTION * cap:
            alerts.append(Alert("claude_budget_80", "P1", f"Claude spend ${spent:.2f} is {spent / cap:.0%} of the ${cap:.2f} monthly cap",
                                "check `getrich agents-status`; agents stop at the cap"))
    except TimeoutError:
        pass  # the database is busy; the next run will check

    alerts += _trading_alerts(now)

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now >= day_start + timedelta(minutes=10):
        expected_latest = day_start - timedelta(days=1)
        try:
            with connect(timeout=5) as con:
                rows = con.execute(
                    "SELECT symbol, max(ts_open) FROM bars WHERE venue='binance' AND timeframe='1d' GROUP BY symbol"
                ).fetchall()
        except TimeoutError:
            rows = []
        from ..trading import instruments

        tracked = set(instruments.symbols("crypto"))                      # only instruments we use: a delisted coin left in the store must not raise alerts forever
        for symbol, latest in rows:
            if symbol in tracked and latest < expected_latest:
                alerts.append(
                    Alert(
                        f"bar_missing:{symbol}",
                        "P1",
                        f"{symbol} daily bar for {expected_latest:%Y-%m-%d} is missing (latest {latest:%Y-%m-%d})",
                        "run `getrich collect-binance`; check Binance connectivity",
                    )
                )
    return alerts


def _trading_alerts(now) -> list[Alert]:
    """Order-path states that must never sit silently in a log. File flags are checked directly, so they clear the moment the owner clears them."""
    from ..trading import book as tbook

    alerts: list[Alert] = []
    if tbook.is_halted():
        alerts.append(Alert("risk_halt_latched", "P1", "the account drawdown halt is latched: new entries are blocked",
                            "review the losses, then `getrich unhalt` only when you decide to resume"))
    if tbook.is_killed():
        alerts.append(Alert("kill_switch_on", "P1", "the kill switch is on: positions were flattened and new entries are blocked",
                            "`getrich unkill` when you are ready"))
    try:
        with connect(timeout=5) as con:
            ingest_events(con)
            since = now - timedelta(hours=24)
            names = dict(con.execute("SELECT event, count(*) FROM events WHERE event IN ('broker.unprotected_position', 'broker.stop_missing') AND ts >= ? GROUP BY 1", [since]).fetchall())
    except TimeoutError:
        names = {}
    if names.get("broker.unprotected_position"):
        alerts.append(Alert("unprotected_position", "P0", "a position may be held WITHOUT a protective stop (stop placement and flattening both failed)",
                            "close it on the venue by hand now; see broker.unprotected_position in data/logs"))
    if names.get("broker.stop_missing"):
        alerts.append(Alert("stop_missing", "P0", "a held position has no resting protective order and no sale: its stop was removed",
                            "check the venue and re-protect or close it; see broker.stop_missing in data/logs"))
    try:                                # paper stops are evaluated from stored hourly bars, so a stale feed with a position open means no stop protection
        st = tbook.load_state(["BTCUSDT"], now)
        if st.positions:
            age = st.prices.get("BTCUSDT", (0, 1e12, ""))
            if age[2] != "1h" or age[1] > 3 * 3600:
                alerts.append(Alert("paper_stops_blind", "P1", "a paper position is open but hourly bars are stale, so its stop is not being checked",
                                    "run `getrich collect-binance --timeframe 1d 1h`"))
    except TimeoutError:
        pass
    return alerts


def _state_path():
    return config.state_dir() / "alerts.json"


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {"active": {}}


def _notify(alert: Alert) -> None:
    if os.environ.get("GETRICH_NOTIFY", "1") == "0":
        return
    text = f"{alert.message}. {alert.action}".replace('"', "'")[:200]
    try:
        proc = subprocess.run(
            ["osascript", "-e", f'display notification "{text}" with title "getrich {alert.severity}"'],
            timeout=5,
            check=False,
            capture_output=True,
            text=True,
        )
        # osascript exits 0 even when macOS later hides the banner, so this proves the call was made,
        # not that you saw it. `getrich ack notification-seen` records that you did.
        emit(
            "watchdog.notified", service=SERVICE, level="info" if proc.returncode == 0 else "warn",
            key=alert.key, severity=alert.severity, returncode=proc.returncode, stderr=(proc.stderr or "")[:200],
        )
    except Exception as exc:  # a failed notification must never crash the watchdog
        emit("watchdog.notified", service=SERVICE, level="warn", key=alert.key, severity=alert.severity, error=repr(exc))


def _ping() -> None:
    url = os.environ.get("GETRICH_HEARTBEAT_URL")
    if not url:
        return
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        if resp.status_code < 400:
            emit("watchdog.pinged", service=SERVICE, status=resp.status_code)
        else:
            emit("watchdog.ping_failed", service=SERVICE, level="warn", status=resp.status_code)
    except Exception as exc:
        emit("watchdog.ping_failed", service=SERVICE, level="warn", error=repr(exc))


def run(notify: bool = True, ping: bool = True) -> list[Alert]:
    now = utcnow()
    alerts = check(now)
    state = _load_state()
    active: dict = state.get("active", {})
    current = {a.key: a for a in alerts}

    for key, a in current.items():
        prev = active.get(key)
        if prev is None:
            emit(
                "alert.raised", service=SERVICE, level="error" if a.severity == "P0" else "warn",
                key=key, severity=a.severity, message=a.message, action=a.action,
            )
        due = prev is None or (
            a.severity in RENOTIFY_SECONDS
            and (now - parse_ts(prev["last_notified"])).total_seconds() > RENOTIFY_SECONDS[a.severity]
        )
        if due and notify and a.severity in ("P0", "P1"):
            _notify(a)
        active[key] = {
            "severity": a.severity,
            "message": a.message,
            "first_ts": prev["first_ts"] if prev else iso(now),
            "last_notified": iso(now) if due else prev["last_notified"],
        }
    for key in list(active):
        if key not in current:
            emit("alert.cleared", service=SERVICE, key=key)
            del active[key]

    _state_path().write_text(json.dumps({"active": active}))
    beat(SERVICE, ok=True, alerts=len(alerts))
    if ping and not any(a.severity in ("P0", "P1") for a in alerts):
        _ping()
    return alerts
