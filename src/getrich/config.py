"""Paths and environment. Everything reads the environment at call time so tests can redirect it."""

from __future__ import annotations

import os
from pathlib import Path


def root() -> Path:
    env = os.environ.get("GETRICH_HOME")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    env = os.environ.get("GETRICH_DATA")
    return Path(env).expanduser() if env else root() / "data"


def logs_dir() -> Path:
    return data_dir() / "logs"


def state_dir() -> Path:
    return data_dir() / "state"


def heartbeat_dir() -> Path:
    return state_dir() / "heartbeats"


def db_path() -> Path:
    return data_dir() / "getrich.duckdb"


def ensure_dirs() -> None:
    for d in (logs_dir(), state_dir(), heartbeat_dir()):
        d.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """Load KEY=VALUE lines from <root>/.env without overriding real environment variables.

    The .env file is gitignored. Keys (Anthropic, heartbeat URL) live there, never in the repo.
    """
    path = root() / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
