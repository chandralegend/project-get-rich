"""Cumulative trial registry (docs/trials.json).

The Deflated Sharpe Ratio only means something if it knows how many variants were tried. Phase 1 counted its
own 8 and Phase 2 its own 5, which understates the project-wide search. This registry holds EVERY strategy or
model variant evaluated so far, with its annualised Sharpe, so each new experiment is deflated against all of them.
It is a plain JSON file in the repo so it can be audited and diffed.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .. import config

DAYS = 365


def path() -> Path:
    return config.root() / "docs" / "trials.json"


def load() -> list[dict]:
    p = path()
    return json.loads(p.read_text()) if p.exists() else []


def period_sharpes(entries: list[dict] | None = None) -> list[float]:
    """Per-period (daily) Sharpe ratios, which is what the Deflated Sharpe expects."""
    entries = load() if entries is None else entries
    return [e["sharpe_annual"] / math.sqrt(DAYS) for e in entries]


def register(phase: int, name: str, sharpe_annual: float, source: str) -> bool:
    """Add a trial unless that name is already recorded. Returns True if added."""
    entries = load()
    if any(e["name"] == name for e in entries):
        return False
    entries.append({"phase": phase, "name": name, "sharpe_annual": round(float(sharpe_annual), 4), "source": source})
    path().write_text(json.dumps(entries, indent=2) + "\n")
    return True
