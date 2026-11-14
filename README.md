# project-get-rich

A local-first research and trading system for crypto, gold and FX, built for personal use. Claude reads the news, a model trained on the collected data scores setups, and a separate risk gate plus a human approve every order.

**Status: Phase 0 (foundations).** Nothing here trades. It collects data, records everything to an event log, and watches itself.

- Design: [ARCHITECTURE.md](ARCHITECTURE.md) and the [diagram page](docs/architecture-map.html)
- Research behind it: [research/00-master-report.md](research/00-master-report.md) (reports 01 to 11 sit beside it)

> Personal research project. Not investment, legal or tax advice, and no performance claims. Anything that trades real money is behind your own manual approval.

## Quick start

```bash
uv sync
uv run pytest                  # 20 tests, offline
uv run getrich collect-binance # closed daily bars for BTCUSDT and ETHUSDT (public API, no key)
uv run getrich collect-news    # central-bank RSS feeds (Fed, ECB, BoE)
uv run getrich watchdog        # run every health check once
uv run getrich status          # the status screen
uv run getrich doctor          # check this Mac against the hardening list
```

Run unattended with launchd (user-level, no sudo). Preview first, then install:

```bash
ops/launchd/install.sh
ops/launchd/install.sh install
```

Keep this folder outside `~/Documents`, `~/Desktop` and `~/Downloads`. macOS blocks background jobs from reading those, and the jobs then fail while manual runs still work. After installing, check that the heartbeat timestamps in `getrich status` keep updating.

Secrets go in a gitignored `.env` file (see `getrich doctor` for the names), never in the repo.

## What exists so far

| Piece | Where |
|---|---|
| Append-only event log with `decision_id`, loaded into DuckDB | `src/getrich/obs/` |
| DuckDB store with a cross-process lock | `src/getrich/store/` |
| Binance klines and central-bank news collectors | `src/getrich/collectors/` |
| Watchdog (alerts P0/P1/P2, external dead-man's-switch ping) and `doctor` | `src/getrich/ops/` |
| launchd jobs | `ops/launchd/` |

News rows keep two clocks, `published_at` (the source's claim) and `ingested_at` (ours). Backtests may only use `ingested_at`.
