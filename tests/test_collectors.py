from datetime import datetime, timezone

import httpx

from getrich.collectors import binance, news
from getrich.obs.heartbeat import read
from getrich.store.db import connect

DAY = 86400_000


def _kline(open_ms: int, close_price="100.0"):
    # Binance kline row layout: open time, o, h, l, c, volume, close time, quote volume, trades, ...
    return [open_ms, "99.0", "101.0", "98.0", close_price, "10.0", open_ms + DAY - 1, "1000.0", 50, "0", "0", "0"]


def _binance_client(rows):
    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["startTime"])
        return httpx.Response(200, json=[r for r in rows if r[0] >= start])

    return httpx.Client(transport=httpx.MockTransport(handler), base_url=binance.BASE)


def test_parse_klines_drops_the_open_bar():
    now_ms = 10 * DAY + 5000
    rows = [_kline(8 * DAY), _kline(9 * DAY), _kline(10 * DAY)]  # last one closes after now
    bars = binance.parse_klines(rows, "BTCUSDT", "1d", datetime.now(timezone.utc), now_ms)
    assert len(bars) == 2
    assert bars[0][3] == datetime.fromtimestamp(8 * DAY / 1000, tz=timezone.utc)


def test_binance_collect_is_idempotent_and_beats():
    rows = [_kline(d * DAY) for d in range(20000, 20010)]  # Oct 2024: after the 2020 start, all closed
    client = _binance_client(rows)
    ok, summary = binance.collect(["BTCUSDT"], client=client, start="2020-01-01")
    assert ok and summary == {"BTCUSDT": 10}
    ok, summary = binance.collect(["BTCUSDT"], client=client)
    assert ok and summary == {"BTCUSDT": 0}  # nothing new, no duplicates
    with connect() as con:
        assert con.execute("SELECT count(*) FROM bars").fetchone()[0] == 10
    assert read("collector.binance")["ok"] is True


def test_binance_failure_marks_run_failed_but_keeps_last_ok():
    good = _binance_client([_kline(20000 * DAY)])
    binance.collect(["BTCUSDT"], client=good)
    first_ok = read("collector.binance")["last_ok_ts"]

    def boom(request):
        return httpx.Response(500)

    bad = httpx.Client(transport=httpx.MockTransport(boom), base_url=binance.BASE)
    ok, _ = binance.collect(["BTCUSDT"], client=bad)
    assert ok is False
    hb = read("collector.binance")
    assert hb["ok"] is False and hb["last_ok_ts"] == first_ok


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Rate decision &amp; statement</title><link>https://example.org/a</link>
<description>&lt;p&gt;Body&lt;/p&gt;</description><pubDate>Wed, 12 Nov 2026 14:00:00 GMT</pubDate></item>
<item><title>Second item</title><link>https://example.org/b</link></item>
</channel></rss>"""


def test_news_dedupes_and_stores_two_clocks():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=RSS)))
    ok, summary = news.collect({"test.feed": "https://example.org/rss"}, client=client)
    assert ok and summary == {"test.feed": 2}
    ok, summary = news.collect({"test.feed": "https://example.org/rss"}, client=client)
    assert summary == {"test.feed": 0}  # same items are not stored twice
    with connect() as con:
        rows = con.execute(
            "SELECT title, summary, published_at, ingested_at FROM news_items ORDER BY title"
        ).fetchall()
    assert rows[0][0] == "Rate decision & statement" and rows[0][1] == "Body"
    assert rows[0][2] is not None and rows[0][3] is not None
    assert rows[1][2] is None  # no pubDate: published_at stays empty, ingested_at is still set
    assert rows[1][3] is not None
