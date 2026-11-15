from datetime import datetime, timedelta, timezone

import httpx
import pytest

from getrich.collectors import yahoo
from getrich.store.db import connect
from getrich.trading import instruments


def chart(rows, start):
    ts = [int((start + timedelta(hours=i)).timestamp()) for i in range(len(rows))]
    cols = list(zip(*rows)) if rows else [[], [], [], []]
    return {"chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"open": list(cols[0]), "high": list(cols[1]), "low": list(cols[2]), "close": list(cols[3])}]}}], "error": None}}


NOW = datetime(2026, 11, 13, 12, 30, tzinfo=timezone.utc)
START = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)


def test_parse_drops_missing_prices_and_unclosed_bars():
    rows = [(1.10, 1.11, 1.09, 1.105), (None, None, None, None), (1.1, 1.12, 1.08, 1.11), (1.1, 1.1, 1.1, 1.1), (1.1, 1.1, 1.1, 1.1)]
    bars = yahoo.parse_chart(chart(rows, START), instruments.get("EURUSD"), "1h", NOW, NOW)
    assert [b[3].hour for b in bars] == [8, 10, 11]            # 12:00 has not closed at 12:30, 09:00 had no price
    assert bars[0][0] == "yahoo" and bars[0][1] == "EURUSD" and bars[0][8] == 0.0


def test_inverted_pairs_are_stored_in_dollars_with_high_and_low_swapped():
    bars = yahoo.parse_chart(chart([(150.0, 152.0, 148.0, 151.0)], START), instruments.get("JPYUSD"), "1h", NOW, NOW)
    _v, sym, _tf, _ts, o, h, l, c, *_ = bars[0]
    assert sym == "JPYUSD" and o == pytest.approx(1 / 150) and h == pytest.approx(1 / 148) and l == pytest.approx(1 / 152) and c == pytest.approx(1 / 151) and h > l


def test_bad_payload_is_an_error():
    with pytest.raises(ValueError):
        yahoo.parse_chart({"chart": {"result": None, "error": {"code": "Not Found"}}}, instruments.get("EURUSD"), "1h", NOW, NOW)


def test_throttling_is_retried_then_succeeds():
    calls, waits = [], []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json={"ok": 1})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert yahoo.fetch(client, "EURUSD=X", "1h", "5d", sleep=waits.append) == {"ok": 1}
    assert len(waits) == 2 and waits[1] > waits[0]


def test_an_empty_body_counts_as_throttling_and_a_404_fails_at_once():
    n = []

    def empty_then_ok(request):
        n.append(1)
        return httpx.Response(200, content=b"") if len(n) == 1 else httpx.Response(200, json={"a": 1})
    assert yahoo.fetch(httpx.Client(transport=httpx.MockTransport(empty_then_ok)), "X", "1h", "5d", sleep=lambda s: None) == {"a": 1}
    with pytest.raises(RuntimeError, match="404"):
        yahoo.fetch(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))), "X", "1h", "5d", sleep=lambda s: None)


def test_collect_stores_bars_once_and_one_failure_does_not_stop_the_rest(monkeypatch):
    good = chart([(1.1, 1.11, 1.09, 1.105)] * 3, datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=6))

    def handler(request):
        return httpx.Response(404) if "GBPUSD" in str(request.url) else httpx.Response(200, json=good)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ok, summary = yahoo.collect(["GBPUSD", "EURUSD"], ["1h"], client=client, pause_s=0, sleep=lambda s: None)
    assert ok is False and summary == {"EURUSD/1h": 3}
    ok, summary = yahoo.collect(["EURUSD"], ["1h"], client=client, pause_s=0, sleep=lambda s: None)
    assert ok and summary == {"EURUSD/1h": 0}                       # idempotent
    with connect() as con:
        assert con.execute("SELECT count(*) FROM bars WHERE venue = 'yahoo'").fetchone()[0] == 3


def test_the_registry_is_consistent_and_forex_closes_for_the_weekend():
    from getrich.trading.types import DEFAULT_RULES
    assert all(i.symbol in DEFAULT_RULES for i in instruments.INSTRUMENTS)
    sat, fri_late, sun_early, sun_late, mon = (datetime(2026, 11, d, h, tzinfo=timezone.utc) for d, h in ((14, 12), (13, 23), (15, 10), (15, 23), (16, 9)))
    assert not instruments.is_open("EURUSD", sat) and not instruments.is_open("XAUUSD", fri_late) and not instruments.is_open("EURUSD", sun_early)
    assert instruments.is_open("EURUSD", sun_late) and instruments.is_open("EURUSD", mon)
    assert all(instruments.is_open("BTCUSDT", t) for t in (sat, sun_early))
    assert instruments.cost_for("EURUSD").round_trip() < instruments.cost_for("BTCUSDT").round_trip()
