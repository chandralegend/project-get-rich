"""Local pre-filter: runs before any API call, costs nothing, and bounds what Claude is ever shown.

  1. near-duplicate removal: word-3-gram Jaccard similarity against items ingested in the previous 48 hours
     (the first copy wins);
  2. a relevance gate: an item must mention something that can move crypto, gold or FX.

Embeddings and a sentiment model are NOT used yet: the model downloads are large on this connection and Phase 3
does not need them. Items dropped here are recorded in `item_processing` so they are never looked at again.
"""

from __future__ import annotations

import re
from datetime import timedelta

from ..obs.events import utcnow

DUP_WINDOW = timedelta(hours=48)
DUP_THRESHOLD = 0.80

RELEVANT = re.compile(
    r"\b(rates?|interest|inflation|cpi|pce|payrolls?|employment|jobs|unemployment|gdp|fomc|fed|federal reserve|ecb|boe|"
    r"bank of england|monetary|yields?|treasur\w*|dollar|usd|euro|sterling|yen|gold|silver|bitcoin|btc|ether\w*|crypto\w*|"
    r"digital assets?|stablecoins?|tether|usdc|etfs?|sec|cftc|regulat\w*|sanctions?|tariffs?|default|liquidity|stress|"
    r"crisis|hack\w*|exploit\w*|binance|exchange|bank run|recession|oil|geopolitic\w*|war)\b",
    re.I,
)
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", (text or "").lower())).strip()


def shingles(text: str, k: int = 3) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    if len(words) < k:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def is_relevant(title: str, summary: str) -> bool:
    return bool(RELEVANT.search(f"{title} {summary}"))


def pending_items(con, limit: int) -> list[dict]:
    """Newest first: with a cap on how many items are classified, the fresh ones must not queue behind a backlog of old ones."""
    rows = con.execute(
        "SELECT n.item_id, n.source, n.title, n.summary, n.published_at, n.ingested_at FROM news_items n "
        "LEFT JOIN item_processing p ON p.item_id = n.item_id WHERE p.item_id IS NULL "
        "ORDER BY n.ingested_at DESC LIMIT ?", [limit],
    ).fetchall()
    return [dict(zip(("item_id", "source", "title", "summary", "published_at", "ingested_at"), r)) for r in rows]


def mark(con, item_id: str, status: str, detail: str = "") -> None:
    con.execute("INSERT OR REPLACE INTO item_processing VALUES (?, ?, ?, ?)", [item_id, status, detail[:300], utcnow()])


def prefilter(con, items: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Marks duplicates and irrelevant items in the database and returns the items worth sending to Claude."""
    keep, counts = [], {"duplicate": 0, "skipped_irrelevant": 0}
    for it in items:
        sh = shingles(it["title"])
        earlier = con.execute(
            "SELECT item_id, title FROM news_items WHERE ingested_at < ? AND ingested_at >= ? AND item_id <> ?",
            [it["ingested_at"], it["ingested_at"] - DUP_WINDOW, it["item_id"]],
        ).fetchall()
        dup_of = next((i for i, t in earlier if jaccard(sh, shingles(t)) >= DUP_THRESHOLD), None)
        if dup_of:
            mark(con, it["item_id"], "duplicate", f"of {dup_of}")
            counts["duplicate"] += 1
        elif not is_relevant(it["title"], it["summary"]):
            mark(con, it["item_id"], "skipped_irrelevant", "no market-relevant term")
            counts["skipped_irrelevant"] += 1
        else:
            keep.append(it)
    return keep, counts
