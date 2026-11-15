"""Risk limits, hash-pinned. The gate refuses to open anything unless config/limits.toml still matches the hash the owner pinned.

`limits-approve` pins the file it writes. Editing the file by hand without pinning again makes every new entry fail closed,
with a message saying why. Exits (reducing a position) are never blocked by this.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .. import config

# Starting points from ARCHITECTURE.md 4.4. They are conservative defaults the owner can tighten (and loosen only by editing here and in docs).
RISK_PER_TRADE = 0.005        # default: 0.5% of equity at risk if the stop is hit. The approved value lives in the pinned limits file (risk_per_trade)
MAX_RISK_PER_TRADE = 0.05     # hard ceiling no file may exceed
MAX_COST_R = 0.25             # round-trip costs may not exceed a quarter of the amount risked
EDGE_COST_MULTIPLE = 3.0      # if a source claims an expected move, it must beat round-trip costs by this multiple
MIN_STOP_FRACTION = 0.005     # stops tighter than 0.5% of price are noise
MAX_STOP_FRACTION = 0.20
PROPOSAL_TTL_S = 15 * 60      # an unapproved proposal goes stale: prices move
MIN_ORDER_LIFETIME_S = 60     # conduct guard: no cancelling an exchange order younger than this (spoofing-like behaviour)
MAX_CANCEL_TO_FILL = 3.0      # conduct guard: cancels per fill over the last 24 hours


@dataclass(frozen=True)
class Limits:
    profile: str
    max_exposure_fraction: float
    account_drawdown_halt: float
    daily_loss_halt: float
    sha256: str
    risk_per_trade: float = RISK_PER_TRADE


def limits_path() -> Path:
    return config.root() / "config" / "limits.toml"


def pin_path() -> Path:
    return config.state_dir() / "limits.pin"


def file_hash(path: Path | None = None) -> str:
    return hashlib.sha256((path or limits_path()).read_bytes()).hexdigest()


def pin() -> str:
    """Record the current file's hash as the approved one. Only the owner runs this, via `limits-approve` or `limits-pin`."""
    h = file_hash()
    config.ensure_dirs()
    pin_path().write_text(h + "\n")
    return h


def load() -> tuple[Limits | None, str]:
    """(limits, "") if the file exists and matches the pin, else (None, reason). Never raises: the gate fails closed on a reason."""
    path = limits_path()
    if not path.exists():
        return None, "config/limits.toml does not exist (run limits-approve)"
    if not pin_path().exists():
        return None, "limits are not pinned (run `getrich limits-pin` after reviewing config/limits.toml)"
    h = file_hash()
    if pin_path().read_text().strip() != h:
        return None, "config/limits.toml changed since it was pinned (approve it again with limits-approve or limits-pin)"
    try:
        d = tomllib.loads(path.read_text())
        lim = Limits(d["profile"], float(d["max_exposure_fraction"]), float(d["account_drawdown_halt"]), float(d["daily_loss_halt"]), h, float(d.get("risk_per_trade", RISK_PER_TRADE)))
    except (KeyError, ValueError, tomllib.TOMLDecodeError) as exc:
        return None, f"config/limits.toml is not valid: {exc!r}"
    if not (0 < lim.max_exposure_fraction <= 1 and 0 < lim.account_drawdown_halt < 1 and 0 < lim.daily_loss_halt < 1 and 0 < lim.risk_per_trade <= MAX_RISK_PER_TRADE):
        return None, "config/limits.toml has values outside their allowed range"
    return lim, ""
