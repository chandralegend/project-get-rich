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

- The main image holds only the runtime dependencies. It cannot train models or run the research workers, and the Claude Agent SDK investigator is not set up in it. The forecasters run in a third container, `models` (below).
- There is no login on the UI. It is published on 127.0.0.1 only, state-changing requests need a header and a local origin, and the approve, kill and halt-reset buttons are the same owner actions the terminal has. Do not publish the port beyond localhost without adding authentication.
- The Phase 0 gate measures watchdog and collector continuity from the event log; there is a gap while the Mac is off or Docker is not running, exactly as before.


## The models service (daily live forecasts)

`models` is its own image (`docker/models.Dockerfile`, about 3.1 GB: CPU torch, Chronos-2, TimesFM 2.5, Kronos-small, LightGBM, the getrich source). It has **no network and no API keys**; the weights (volume `getrich-models-hf`), the lock file and the reviewed Kronos source are mounted read-only; it shares the data volume to read bars and write the forecast caches. Its scheduler (`getrich scheduler --only models`) runs `forecast-live` hourly; the job is idempotent, so it does nothing until a new daily bar exists and then adds one forecast per model for BTC and ETH (about two minutes, Kronos is most of it). State is in `data/state/scheduler-models.json`; the System screen shows each model's newest origin.

First time (or after a Docker reset): `scripts/models-weights` copies the four weight sets from the host's Hugging Face cache into the volume and verifies every file against `config/forecast_models.lock.json`. Every run verifies the weights again before a worker starts and refuses on a mismatch. After code changes: `docker compose build models && docker compose up -d models`.

Honest limits: Chronos-2 and TimesFM reproduce the Mac's results exactly. Kronos draws 12 samples, so its numbers differ run to run and between a CPU and the Mac's GPU; the research history was every 5th day on the GPU, the live origins are daily on CPU. None of these forecasters beat a random walk (docs/forecast-eval.md); they are shown, not trusted.

### The PI-Net forward study (also in the models container)

`pinet-live` runs hourly next to `forecast-live` (idempotent). Once the day's Chronos-2 forecast and the whole day's hourly bars exist, the frozen model `pinet-lgbm-chronos2-nonews.pkl` (hash pinned in the pre-registration) scores BTC and ETH, and each call goes into the ledger with its exact inputs; earlier in-domain decisions are resolved against the daily bars that followed. It refuses to record anything unless `docs/preregistration-pinet-forward.md` has been logged (`scripts/gr preregister docs/preregistration-pinet-forward.md`, done 2026-11-16, hash `7eafcb5a...`) and the model file matches the pinned hash. The verdict is computed once, at 180 days and 150 resolved decisions: `scripts/gr pinet-verdict`. The System screen shows today's call per coin and the running record, clearly marked as interim.
