"""News collector for public central-bank RSS feeds.

Every item is stored with two clocks: published_at (the source's claim) and ingested_at (ours).
Only ingested_at is allowed in backtests. Crypto and wire-service feeds are deliberately NOT included
yet: their terms on storage and LLM use have not been read.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone

import feedparser
import httpx

from ..ids import new_id
from ..obs.events import emit, utcnow
from ..obs.heartbeat import beat
from ..store.db import connect

SERVICE = "collector.news"
HEADERS = {"User-Agent": "getrich-research/0.1"}
DEFAULT_FEEDS = {
    "fed.press": "https://www.federalreserve.gov/feeds/press_all.xml",
    "ecb.press": "https://www.ecb.europa.eu/rss/press.html",
    "boe.news": "https://www.bankofengland.co.uk/rss/news",
}

_TAG = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    return html.unescape(_TAG.sub("", text or "")).strip()


def _published(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def parse_feed(source: str, content: bytes) -> list[dict]:
    items = []
    for e in feedparser.parse(content).entries:
        title = _clean(e.get("title"))
        if not title:
            continue
        link = e.get("link") or ""
        items.append(
            {
                "source": source,
                "url": link,
                "title": title,
                "summary": _clean(e.get("summary"))[:2000],
                "published_at": _published(e),
                "content_hash": hashlib.sha256(f"{source}|{link or title}".encode()).hexdigest(),
            }
        )
    return items


def collect(feeds: dict[str, str] | None = None, client: httpx.Client | None = None) -> tuple[bool, dict[str, int]]:
    feeds = feeds or DEFAULT_FEEDS
    own = client is None
    client = client or httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True)
    ok, summary = True, {}
    try:
        for source, url in feeds.items():
            try:
                resp = client.get(url)
                resp.raise_for_status()
                items = parse_feed(source, resp.content)
            except Exception as exc:
                ok = False
                emit("collector.error", service=SERVICE, level="error", source=source, error=repr(exc))
                continue
            new_rows = []
            with connect() as con:
                for it in items:
                    if con.execute("SELECT 1 FROM news_items WHERE content_hash = ?", [it["content_hash"]]).fetchone():
                        continue
                    row = (
                        new_id("n"), it["source"], it["url"], it["title"], it["summary"],
                        it["published_at"], utcnow(), it["content_hash"],
                    )
                    con.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?)", row)
                    new_rows.append(row)
            for row in new_rows:  # events are written after the lock is released
                emit(
                    "news.ingested", service=SERVICE, item_id=row[0], source=row[1], title=row[3],
                    published_at=row[5], ingested_at=row[6],
                )
            summary[source] = len(new_rows)
    finally:
        if own:
            client.close()
    emit("collector.run", service=SERVICE, ok=ok, new_items=summary)
    beat(SERVICE, ok=ok, new_items=sum(summary.values()))
    return ok, summary
