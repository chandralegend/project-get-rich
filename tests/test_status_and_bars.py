from datetime import datetime, timedelta, timezone

from rich.console import Console

from getrich.obs import status
from getrich.obs.heartbeat import beat
from getrich.ops import watchdog
from getrich.store.db import connect


def _insert_bar(ts_open: datetime):
    with connect() as con:
        con.execute(
            "INSERT INTO bars VALUES ('binance','BTCUSDT','1d',?,1,1,1,1,1,1,1,?)",
            [ts_open, ts_open],
        )


def test_missing_daily_bar_is_p1_once_the_grace_period_has_passed():
    beat("collector.binance", ok=True)
    beat("collector.news", ok=True)
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    _insert_bar(datetime(2026, 11, 12, tzinfo=timezone.utc))  # yesterday's bar (Nov 13) is missing
    keys = {a.key: a for a in watchdog.check(now)}
    assert keys["bar_missing:BTCUSDT"].severity == "P1"


def test_up_to_date_bars_raise_nothing():
    beat("collector.binance", ok=True)
    beat("collector.news", ok=True)
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    _insert_bar(datetime(2026, 11, 13, tzinfo=timezone.utc))
    assert not [a for a in watchdog.check(now) if a.key.startswith("bar_missing")]


def test_no_bar_alert_in_the_first_minutes_after_midnight_utc():
    beat("collector.binance", ok=True)
    beat("collector.news", ok=True)
    now = datetime(2026, 11, 14, 0, 5, tzinfo=timezone.utc)  # collector may not have run yet
    _insert_bar(datetime(2026, 11, 12, tzinfo=timezone.utc))
    assert not [a for a in watchdog.check(now) if a.key.startswith("bar_missing")]


def test_status_screen_renders_on_an_empty_system():
    console = Console(record=True, width=120)
    status.render(console)
    text = console.export_text()
    assert "getrich status" in text
    assert "HEALTH" in text and "not built yet" in text
    assert "no bars yet" in text


def test_status_screen_shows_bars_and_news_counts():
    _insert_bar(datetime.now(timezone.utc) - timedelta(days=1))
    beat("collector.binance", ok=True)
    console = Console(record=True, width=120)
    status.render(console)
    assert "BTCUSDT 1d: 1 bars" in console.export_text()
