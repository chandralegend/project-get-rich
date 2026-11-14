"""Open web news: GDELT and Google News RSS. This is how God's Eye View gets its news layer too (GDELT's raw 15-minute
files as the keyless backbone, Google News RSS for headlines), here filtered to crypto, gold, FX and rates.

GDELT is read from its raw GKG files (about 2.5 MB every 15 minutes, no key), not its search API: from this connection
the search API answered 429 even for single requests spaced 12 seconds apart. Each GKG row carries the article URL,
source domain, page title and an average tone; rows are kept only if the title matches a topic pattern and is English.

Both are headline-level: a title, an outlet and a timestamp, no article text. That is enough for Haiku to classify
an event, and the extractor's near-duplicate filter collapses the many outlets that carry the same story.
Everything is third-party text of unknown quality and goes through the same sanitiser and injection checks as any
other news item. Items are stored with two clocks like all news: published_at (the source's claim), ingested_at (ours).

Terms: not assessed here by decision of the owner, who reviews them. Findings from a read on 2026-11-14 are in
docs/news-feed-terms.md for reference.
"""

from __future__ import annotations

import hashlib
import html
import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import httpx

from ..llm import safety
from ..obs.events import emit
from ..obs.heartbeat import beat
from . import news

SERVICE = "collector.webnews"
HEADERS = {"User-Agent": "getrich-research/0.1"}
GDELT_LASTUPDATE = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GNEWS_URL = "https://news.google.com/rss/search"
GKG_SLOTS = 5                          # 15-minute files fetched per run (about an hour and a quarter); repeats are deduped
GDELT_MAX_PER_RUN = 80                 # bounds the extraction bill; the extractor drops near-duplicates and irrelevant items too
PER_QUERY = 15                         # newest Google News items per query

TOPIC = re.compile(
    r"\b(bitcoin|btc|ethereum|ether|crypto\w*|stablecoins?|tether|usdc|binance|coinbase|kraken|"
    r"gold (prices?|futures|rally|slump|rate)|spot gold|bullion|federal reserve|fomc|fed (rates?|hike|cut|chair|officials?)|"
    r"ecb|bank of england|bank of japan|boj|yen|us dollar|u\.s\. dollar|dollar index|treasury yields?)\b", re.I)
GNEWS_QUERIES = [
    "bitcoin", "ethereum", "stablecoin", "crypto regulation", "crypto exchange hack", "gold price",
    "federal reserve interest rates", "dollar yen euro currency",
]
_TITLE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.S)


def _gdelt_time(text: str | None) -> datetime | None:
    try:
        return datetime.strptime(text or "", "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_gkg(raw: bytes) -> list[dict]:
    """Rows of a GKG 2.1 file (tab separated, 27 columns) that look like crypto, gold, FX or central-bank news in English."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        text = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    except (zipfile.BadZipFile, IndexError, KeyError):
        raise RuntimeError("gdelt file is not a readable zip")
    items = []
    for line in text.splitlines():
        f = line.split("\t")
        if len(f) < 27 or f[25].strip():                       # column 25 is translation info: non-English rows carry it
            continue
        m = _TITLE.search(f[26])
        title, url = safety.sanitize(html.unescape(m.group(1)) if m else "", 300), f[4]
        if not title or not url.startswith("http") or not TOPIC.search(title):
            continue
        domain = f[3][:60] or "web"
        tone = f[15].split(",")[0] if f[15] else ""
        try:
            tone = f"{float(tone):+.1f}"
        except ValueError:
            tone = "n/a"
        items.append({"source": f"gdelt:{domain}", "url": url, "title": title, "summary": f"{domain}; GDELT average tone {tone}",
                      "published_at": _gdelt_time(f[1]),
                      "content_hash": hashlib.sha256(f"gdelt|{url}".encode()).hexdigest()})
    return items


def gkg_urls(client: httpx.Client, slots: int = GKG_SLOTS) -> list[str]:
    """The latest GKG file from GDELT's index, then the slots before it (files are named by 15-minute timestamp)."""
    resp = client.get(GDELT_LASTUPDATE)
    resp.raise_for_status()
    latest = next((ln.split()[2] for ln in resp.text.splitlines() if ln.strip().endswith(".gkg.csv.zip")), None)
    if not latest:
        raise RuntimeError("gdelt lastupdate.txt has no gkg file")
    stamp = _gdelt_time(latest.rsplit("/", 1)[1].split(".")[0])
    base = latest.rsplit("/", 1)[0]
    return [f"{base}/{stamp - timedelta(minutes=15 * i):%Y%m%d%H%M%S}.gkg.csv.zip" for i in range(slots)]


def fetch_gdelt(client: httpx.Client) -> tuple[list[dict], int]:
    """Items from the recent GKG files and how many files could not be read (a missing slot is not an outage)."""
    items, bad = [], 0
    for url in gkg_urls(client):
        try:
            r = client.get(url)
            r.raise_for_status()
            items += parse_gkg(r.content)
        except Exception:
            bad += 1
    return items[:GDELT_MAX_PER_RUN], bad


def parse_gnews(content: bytes) -> list[dict]:
    items = []
    for e in feedparser.parse(content).entries:
        title, link = safety.sanitize(html.unescape(e.get("title") or ""), 300), e.get("link") or ""
        if not title or not link:
            continue
        outlet = safety.sanitize((e.get("source") or {}).get("title", ""), 80)
        items.append({"source": "gnews", "url": link, "title": title, "summary": outlet,
                      "published_at": news._published(e),
                      "content_hash": hashlib.sha256(f"gnews|{title}|{outlet}".encode()).hexdigest()})
    return items


def fetch_gnews(client: httpx.Client, query: str) -> list[dict]:
    resp = client.get(f"{GNEWS_URL}?q={quote_plus(query + ' when:1d')}&hl=en-US&gl=US&ceid=US:en")
    resp.raise_for_status()
    return parse_gnews(resp.content)[:PER_QUERY]


def collect(client: httpx.Client | None = None, *, gnews_queries=None, gkg_slots: int | None = None) -> tuple[bool, dict]:
    """A failing source does not stop the other. ok is False if anything failed, but the watchdog heartbeat only reports
    unhealthy when nothing at all could be read, since GDELT and Google News each have bad days."""
    own = client is None
    client = client or httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True)
    queries = GNEWS_QUERIES if gnews_queries is None else gnews_queries
    ok, summary = True, {"gdelt": 0, "gnews": 0, "failed": 0}
    sources_ok = 0
    try:
        try:
            items, bad_files = fetch_gdelt(client)
            summary["gdelt"] = len(news.store_items(items))
            if bad_files < (gkg_slots or GKG_SLOTS):
                sources_ok += 1
            if bad_files:
                ok = False
        except Exception as exc:
            ok, summary["failed"] = False, summary["failed"] + 1
            emit("collector.error", service=SERVICE, level="error", source="gdelt", error=repr(exc)[:200])
        gnews_failed = 0
        for q in queries:
            try:
                summary["gnews"] += len(news.store_items(fetch_gnews(client, q)))
            except Exception as exc:
                ok, gnews_failed = False, gnews_failed + 1
                emit("collector.error", service=SERVICE, level="error", source="gnews", query=q, error=repr(exc)[:200])
        summary["failed"] += gnews_failed
        if queries and gnews_failed < len(queries):
            sources_ok += 1
    finally:
        if own:
            client.close()
    healthy = sources_ok > 0
    emit("collector.run", service=SERVICE, ok=healthy, new_items=summary)
    beat(SERVICE, ok=healthy, new_items=summary["gdelt"] + summary["gnews"])
    return ok, summary
