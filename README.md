# project-get-rich

A local-first research and trading system for crypto, gold and FX, built for personal use. Claude reads the news, a model trained on the collected data scores setups, and a separate risk gate plus a human approve every order.

**Status: Phase 0 (foundations) finishing, Phase 1 (evaluation harness) built.** Nothing here trades. It collects data, records everything to an event log, and watches itself. What is left to finish Phase 0 is in [docs/phase0-checklist.md](docs/phase0-checklist.md).

- Design: [ARCHITECTURE.md](ARCHITECTURE.md) and the [diagram page](docs/architecture-map.html)
- Research behind it: [research/00-master-report.md](research/00-master-report.md) (reports 01 to 11 sit beside it)

> Personal research project. Not investment, legal or tax advice, and no performance claims. Anything that trades real money is behind your own manual approval.

## Quick start

```bash
uv sync
uv run pytest                  # 103 tests, offline
uv run getrich collect-binance # closed daily bars for BTCUSDT and ETHUSDT (public API, no key)
uv run getrich collect-news    # central-bank RSS feeds (Fed, ECB, BoE)
uv run getrich watchdog        # run every health check once
uv run getrich status          # the status screen
uv run getrich doctor          # check this Mac against the hardening list
uv run getrich gate            # is Phase 0 finished? checks the event log for evidence
uv run getrich ack <item>      # record something only you can confirm (see the checklist)
uv run getrich ledger-verify   # verify the insight ledger's hash chain
uv run getrich validate-harness  # prove the evaluation harness can tell skill from luck
uv run getrich run-baselines   # baseline strategies on stored BTC/ETH data
uv run getrich derive-limits   # proposed risk limits derived from that history
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
| Hash-chained insight ledger (writes arrive in Phase 3) | `src/getrich/store/ledger.py` |
| Phase 0 exit gate and manual acknowledgements | `src/getrich/ops/gate.py` |
| Compute benchmark | `scripts/bench_compute.py`, `docs/benchmark-m4.md` |
| Evaluation harness: costs, purged CV and CPCV, Deflated Sharpe, triple-barrier labels, backtest, trend and HAR baselines, limit derivation | `src/getrich/eval/`, [docs/phase1-findings.md](docs/phase1-findings.md) |

News rows keep two clocks, `published_at` (the source's claim) and `ingested_at` (ours). Backtests may only use `ingested_at`.
