"""`getrich doctor`: checks the Mac and the project against the hardening list in ARCHITECTURE.md 4.6."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from .. import config


def _pmset() -> dict[str, str]:
    try:
        out = subprocess.run(["pmset", "-g"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    result = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\w+)\s+(.*)", line)
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def _caffeinate_running() -> bool:
    try:
        out = subprocess.run(["pgrep", "-x", "caffeinate"], capture_output=True, text=True, timeout=5)
        return out.returncode == 0
    except Exception:
        return False


def run() -> list[tuple[str, str, str]]:
    """Returns (status, check, detail). status is OK, WARN or TODO."""
    rows: list[tuple[str, str, str]] = []
    rows.append(("OK", "python", sys.version.split()[0]))
    free_gib = shutil.disk_usage(config.root()).free / 2**30
    rows.append(("OK" if free_gib >= 10 else "WARN", "disk free", f"{free_gib:.1f} GiB"))

    pm = _pmset()
    sleep_val = pm.get("sleep", "?")
    if sleep_val.split()[0] == "0" or _caffeinate_running():
        rows.append(("OK", "system sleep", "disabled (pmset sleep 0 or caffeinate running)"))
    else:
        rows.append((
            "TODO", "system sleep",
            f"pmset says sleep={sleep_val}. Install the caffeinate LaunchAgent (no sudo) or run: sudo pmset -a sleep 0",
        ))
    if pm.get("autorestart", "0") == "1":
        rows.append(("OK", "restart after power loss", "on"))
    else:
        rows.append((
            "TODO", "restart after power loss",
            "off. Mac mini: System Settings > Energy > 'Start up automatically after a power failure'",
        ))
    rows.append((
        "TODO", "macOS update reboots",
        "check manually: System Settings > General > Software Update > (i) > turn off 'Install macOS updates' automatic install",
    ))
    rows.append(("OK" if os.environ.get("GETRICH_HEARTBEAT_URL") else "TODO", "external heartbeat",
                 "GETRICH_HEARTBEAT_URL set" if os.environ.get("GETRICH_HEARTBEAT_URL")
                 else "not set: create a dead-man's-switch check yourself and put its ping URL in .env"))
    rows.append(("OK" if os.environ.get("ANTHROPIC_API_KEY") else "TODO", "Anthropic key",
                 "set" if os.environ.get("ANTHROPIC_API_KEY") else "not set (needed from Phase 3; put it in .env)"))
    return rows
