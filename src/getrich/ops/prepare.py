"""Bring the trader's inputs up to date before it plans: market data, news, and the classification of that news.

A plan made on yesterday's headlines is worse than no plan, and the hourly scheduler jobs can be up to an hour behind (or, for the classification, held
back by a daily cap). So a trader run does this first. Every step is allowed to fail on its own: a feed that is down is reported in the packet's
`freshness` section (the trader is told, and discounts that input) and never stops the run. Steps run one after another, in this process, with no
database connection held between them (the store lock is not reentrant and parallel collectors were seen to time out on it).

Not here, on purpose: the forecasters and the PI-Net. They need the heavy research environment (torch, model weights) that the Docker image leaves out.
"""

from __future__ import annotations

import time

from ..obs.events import emit, utcnow
from ..store.db import connect
from . import refresh

SERVICE = "ops.prepare"
EXTRACT_LIMIT = 60                     # newest first; a full hour of headlines is far fewer than this
BRIEFING_MAX_AGE_H = 8                 # a new briefing is written (one Sonnet call, a few cents) when the last one is older


def _step(report: dict, name: str, fn) -> None:
    t0 = time.monotonic()
    try:
        detail = fn()
        report[name] = {"ok": True, "seconds": round(time.monotonic() - t0, 1), "detail": detail}
    except Exception as exc:                                           # one broken source must not stop the run
        report[name] = {"ok": False, "seconds": round(time.monotonic() - t0, 1), "error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _briefing_age_hours() -> float | None:
    with connect() as con:
        row = con.execute("SELECT max(as_of) FROM insights WHERE json_extract_string(payload, '$.kind') = 'briefing'").fetchone()
    return None if not row or row[0] is None else (utcnow() - row[0]).total_seconds() / 3600


def run(classes: tuple[str, ...] | None = None, *, briefing_max_age_h: float = BRIEFING_MAX_AGE_H) -> dict:
    report: dict = {}

    def market():
        res = refresh.run(classes)
        if not res["ok"]:
            raise RuntimeError(f"some collectors failed ({res['rows_added']})")
        return res["rows_added"]

    def collect(module: str):
        def go():
            from ..collectors import news, webnews

            ok, summary = {"news": news, "webnews": webnews}[module].collect()
            if not ok:
                raise RuntimeError(f"partial: {summary}")
            return summary
        return go

    def extract():
        from ..agents import extract as ex

        res = ex.extract_pending(limit=EXTRACT_LIMIT)
        return {k: res[k] for k in ("considered", "recorded", "model_irrelevant", "duplicate", "skipped_irrelevant", "failed", "stopped") if res.get(k) not in (None, 0)}

    def briefing():
        from ..agents import briefing as br

        age = _briefing_age_hours()
        if age is not None and age < briefing_max_age_h:
            return {"skipped": f"last briefing is {age:.1f} h old"}
        res = br.run()
        if res.get("skipped"):
            raise RuntimeError(res["skipped"])
        return {"recorded": res.get("recorded")}

    _step(report, "market_data", market)
    _step(report, "news_feeds", collect("news"))
    _step(report, "web_news", collect("webnews"))
    _step(report, "classify_news", extract)
    _step(report, "briefing", briefing)
    emit("ops.prepare", service=SERVICE, ok=all(v["ok"] for v in report.values()), failed=[k for k, v in report.items() if not v["ok"]])
    return {"ran_at": utcnow().strftime("%Y-%m-%d %H:%M UTC"), "steps": report}
