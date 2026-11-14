"""Sortable ids. A decision_id threads every event a decision touches (see ARCHITECTURE.md 4.7)."""

from __future__ import annotations

import secrets
import time


def new_id(prefix: str) -> str:
    """Prefix + millisecond timestamp (hex, sortable) + 4 random hex chars. Example: n_019a3c2f4b1e7d3a."""
    return f"{prefix}_{int(time.time() * 1000):011x}{secrets.token_hex(2)}"
