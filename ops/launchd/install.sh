#!/usr/bin/env bash
# Install, remove or preview the getrich LaunchAgents (user-level, no sudo).
#   ops/launchd/install.sh            preview what would be installed (default, changes nothing)
#   ops/launchd/install.sh install    copy plists to ~/Library/LaunchAgents and load them
#   ops/launchd/install.sh uninstall  unload and remove them
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$HERE/../.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=(com.getrich.caffeinate com.getrich.collect-binance com.getrich.collect-news com.getrich.collect-webnews com.getrich.paper-tick com.getrich.watchdog)
# The agent jobs call the Claude API, so they are installed separately, only once ANTHROPIC_API_KEY is in .env
LABELS_AGENTS=(com.getrich.agents-extract com.getrich.agents-briefing com.getrich.agents-score)
ACTION="${1:-preview}"

case "$ACTION" in
  preview)
    echo "Project: $PROJECT"
    echo "Would install into $AGENTS:"
    for l in "${LABELS[@]}"; do echo "  $l.plist"; done
    echo "Run '$0 install' to proceed."
    ;;
  install)
    [ -x "$PROJECT/.venv/bin/getrich" ] || { echo "Run 'uv sync' first: $PROJECT/.venv/bin/getrich is missing" >&2; exit 1; }
    mkdir -p "$AGENTS" "$PROJECT/data/logs"
    for l in "${LABELS[@]}"; do
      sed "s#__PROJECT__#$PROJECT#g" "$HERE/$l.plist" > "$AGENTS/$l.plist"
      launchctl bootout "gui/$UID_NUM/$l" 2>/dev/null || true
      launchctl bootstrap "gui/$UID_NUM" "$AGENTS/$l.plist"
      echo "loaded $l"
    done
    ;;
  uninstall)
    for l in "${LABELS[@]}"; do
      launchctl bootout "gui/$UID_NUM/$l" 2>/dev/null || true
      rm -f "$AGENTS/$l.plist"
      echo "removed $l"
    done
    ;;
  install-agents)
    [ -x "$PROJECT/.venv/bin/getrich" ] || { echo "Run 'uv sync' first" >&2; exit 1; }
    grep -q '^ANTHROPIC_API_KEY=' "$PROJECT/.env" 2>/dev/null || { echo "Add ANTHROPIC_API_KEY=... to $PROJECT/.env first (the jobs would fail without it)" >&2; exit 1; }
    mkdir -p "$AGENTS" "$PROJECT/data/logs"
    for l in "${LABELS_AGENTS[@]}"; do
      sed "s#__PROJECT__#$PROJECT#g" "$HERE/$l.plist" > "$AGENTS/$l.plist"
      launchctl bootout "gui/$UID_NUM/$l" 2>/dev/null || true
      launchctl bootstrap "gui/$UID_NUM" "$AGENTS/$l.plist"
      echo "loaded $l"
    done
    ;;
  uninstall-agents)
    for l in "${LABELS_AGENTS[@]}"; do
      launchctl bootout "gui/$UID_NUM/$l" 2>/dev/null || true
      rm -f "$AGENTS/$l.plist"
      echo "removed $l"
    done
    ;;
  *) echo "usage: $0 [preview|install|uninstall|install-agents|uninstall-agents]" >&2; exit 2 ;;
esac
