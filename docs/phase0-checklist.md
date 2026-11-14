# Phase 0 checklist

Phase 0 is finished when `uv run getrich gate` prints `PHASE 0 GATE: PASS`. The gate reads the event log and the store, so every line below is checked by evidence, except the two items only you can confirm.

## Status

| Item | How it is checked | Status |
|---|---|---|
| Repo, store, collectors, tests | `uv run pytest` (38 tests) | Done |
| Append-only event log with `decision_id` | tests, `getrich status` | Done |
| Hash-chained insight ledger | tests, `getrich ledger-verify`, watchdog P0 if broken | Done |
| Collectors and watchdog under launchd | gate: runs and continuity | Running since 2026-11-14 09:41 UTC |
| Kill test (fault, alert, recovery) | gate: `fault -> alert -> recovery` | Passed 2026-11-14 |
| Notification and ping results logged | `watchdog.notified` and `watchdog.pinged` events | Done |
| Compute benchmark, all 7 cases | gate: `compute benchmark` | Done ([results](benchmark-m4.md)) |
| Mac does not sleep | gate (caffeinate job) | Done |
| `libomp` for LightGBM | gate | Done |
| **One unattended week** | gate: `one-week window` | Waiting: earliest pass 2026-11-21 09:41 UTC |
| **External heartbeat** | gate: `external heartbeat` | **You: step 1** |
| **Restart after power loss** | gate (reads `pmset`) | **You: step 2** |
| **Update reboots off** | `getrich ack update-reboots-off` | **You: step 3** |
| **Notification appeared** | `getrich ack notification-seen` | **You: step 4** |

## What only you can do

These touch your accounts or Mac system settings, so I did not do them.

1. **External heartbeat (about 5 minutes).** Without it, if the whole Mac goes down nothing alerts you, because the watchdog runs on the same Mac.
   - Sign up for a dead-man's-switch service that gives you an HTTP ping URL and tells you when pings stop (Healthchecks.io is one; check its current plan limits yourself).
   - Create a check that expects a ping every minute, with a grace period of about 5 minutes, and choose how it contacts you (email, push, SMS).
   - Put the ping URL in `/Users/chandralegend/Developer/project-get-rich/.env` as `GETRICH_HEARTBEAT_URL=...`. The file is gitignored. Treat the URL like a password and never paste it into a chat or commit it.
   - The launchd jobs read `.env` automatically. Check with `uv run getrich gate`: after a minute `external heartbeat` should say PASS.
2. **Restart after power loss.** System Settings, then Energy, then turn on "Start up automatically after a power failure". Or run `sudo pmset -a autorestart 1`. Check with `uv run getrich doctor`.
3. **Automatic macOS update reboots.** System Settings, General, Software Update, click the (i) next to Automatic Updates, and turn off "Install macOS updates". Leave security responses and system files on. Then run `uv run getrich ack update-reboots-off`.
4. **Notification check.** Run the test below. If a banner titled "getrich P1" appears, run `uv run getrich ack notification-seen`. If nothing appears, open System Settings, Notifications, find Script Editor and allow notifications, then try again.

   ```bash
   GETRICH_NOTIFY=1 uv run python -I -c "from getrich.ops.watchdog import _notify, Alert; _notify(Alert('manual-test','P1','Test notification from getrich','No action needed'))"
   ```

## Reading the gate

- `PASS`: true now, with evidence.
- `PENDING`: not yet true. It will become true with time or after your action.
- `MANUAL`: only you can confirm it. `getrich ack <item>` records your statement in the event log. It is an attestation, not a machine check.
- `WARN`: passes, but look at it.
- `FAIL`: broken. Fix it before trusting anything built on top.

Thresholds (3 hours between successful collector runs, 99% watchdog minutes covered with no gap over 15 minutes) are my suggested starting points and live in `src/getrich/ops/gate.py`.
