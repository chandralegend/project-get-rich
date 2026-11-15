# Running the whole system in Docker

Since 2026-11-15 the system runs in two containers from one image (`getrich:local`):

| Service | What it runs |
|---|---|
| `api` | the web UI and API on **http://127.0.0.1:8420** (localhost only, no login) |
| `scheduler` | the jobs launchd used to run: watchdog every minute, paper tick, data refresh (Binance, Yahoo), news, web news, Claude extraction hourly, daily briefing 06:00, daily scoring 07:00 (container time zone Asia/Colombo) |

Never scheduled, on purpose: the trader (manual only, from the Trader screen or `scripts/gr trader`), anything that places, approves or rejects orders, and the kill switch. Caffeinate stays a host job: a container cannot keep the Mac awake.

## Commands

```bash
docker compose up -d --build      # build and start everything
docker compose ps                 # state and health
docker compose logs -f scheduler  # what the jobs are doing
docker compose down               # stop (the data volume stays)
scripts/gr status                 # any getrich command, against the live data
```

Docker Desktop has to start at login for the system to survive a reboot (Docker Desktop settings, General, "Start Docker Desktop when you sign in"); the containers themselves restart on their own (`restart: unless-stopped`).

## Where things live

- **Data** (database, logs, state, briefings, trader plans, forecasts caches) is in the named volume `getrich-data`, mounted at `/data`. A named volume is used instead of the `data/` folder because the database lock needs real file locking, which macOS bind mounts do not reliably give across containers. Per-service logs are in `/data/logs` (`job-<name>.log`).
- **Limits** are `config/limits.toml` on the host, mounted into the containers; the hash pin lives in the volume. To change limits, run `scripts/gr limits-approve ...` so the pin is written where the gate reads it. The pinned limits at cutover are unchanged (moderate).
- **Docs and research** are mounted read-only from the host so the Research screen shows the current files.
- **Secrets** come from the gitignored `.env` (`env_file`); nothing secret is baked into the image. The API key reaches the containers as an environment variable.
- **The trader scope** is `GETRICH_TRADER_CLASSES` (default `crypto` in the compose file, "for now").

## What changed at the cutover

The host launchd jobs were switched off (their plists moved to `~/Library/LaunchAgents.getrich-disabled/`; caffeinate stays). The host `data/` folder was copied into the volume under the database lock and is now a stale backup: the host `getrich` command reads it, not the volume. Use `scripts/gr` for anything that should touch live data. Research runs on the host (replays, pre-registered studies) read the host copy; to refresh it, copy the volume out (`docker run --rm -v getrich-data:/data -v "$PWD/data-export:/out" --entrypoint cp getrich:local /data/getrich.duckdb /out/`) while the stack is stopped.

To go back to launchd: `docker compose down`, move the plists back from `~/Library/LaunchAgents.getrich-disabled/`, run `ops/launchd/install.sh install` and `install-agents`, and copy the database back from the volume first if you want the data gathered in Docker.

## Limits of this setup

- The image holds only the runtime dependencies. It cannot train models or run the research workers (torch, lightgbm, forecasting weights stay on the host), and the Claude Agent SDK investigator is not set up in it.
- There is no login on the UI. It is published on 127.0.0.1 only, state-changing requests need a header and a local origin, and the approve, kill and halt-reset buttons are the same owner actions the terminal has. Do not publish the port beyond localhost without adding authentication.
- The Phase 0 gate measures watchdog and collector continuity from the event log; there is a gap while the Mac is off or Docker is not running, exactly as before.
