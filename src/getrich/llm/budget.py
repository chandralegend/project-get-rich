"""Hard monthly spend cap for Claude API calls, enforced in code before every call.

Spend is read back from the event log (`llm.call` events carry their computed cost), so it survives restarts and
cannot be reset by a crash. The cap defaults to $30 (the owner's choice) and can be lowered with
GETRICH_CLAUDE_MONTHLY_CAP_USD. A call is refused when month-to-date spend plus its worst-case cost would pass the cap.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from ..obs.events import utcnow
from ..obs.ingest import ingest_events
from ..store.db import connect

DEFAULT_CAP_USD = 30.0
WARN_FRACTION = 0.80


class BudgetExceeded(RuntimeError):
    pass


def monthly_cap() -> float:
    return float(os.environ.get("GETRICH_CLAUDE_MONTHLY_CAP_USD", DEFAULT_CAP_USD))


def month_spend_con(con, now: datetime | None = None) -> float:
    """Month-to-date spend using an already-open connection (never open a second one: the lock is not re-entrant)."""
    now = now or utcnow()
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    ingest_events(con)
    row = con.execute(
        "SELECT coalesce(sum(CAST(json_extract(data, '$.cost_usd') AS DOUBLE)), 0) FROM events "
        "WHERE event = 'llm.call' AND ts >= ?",
        [start],
    ).fetchone()
    return float(row[0])


def month_spend(now: datetime | None = None) -> float:
    with connect() as con:
        return month_spend_con(con, now)


def check(estimated_cost: float, now: datetime | None = None) -> float:
    """Raises BudgetExceeded if this call could take the month past the cap. Returns month-to-date spend."""
    spent, cap = month_spend(now), monthly_cap()
    if spent + estimated_cost > cap:
        raise BudgetExceeded(f"monthly cap ${cap:.2f} would be exceeded: spent ${spent:.4f} + up to ${estimated_cost:.4f}")
    return spent


def status(now: datetime | None = None) -> dict:
    spent, cap = month_spend(now), monthly_cap()
    return {"spent": spent, "cap": cap, "fraction": spent / cap if cap else 1.0}
