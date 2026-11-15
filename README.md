# project-get-rich

A local-first research and trading system for crypto, gold and FX, built for personal use. Claude reads the news, a model trained on the collected data scores setups, and a separate risk gate plus a human approve every order.

**Status: Phase 0 (foundations) finishing, Phases 1 to 3 built. No model has shown a detectable edge ([Phase 2](docs/phase2-findings.md), [Phase 3](docs/phase3-findings.md)); the Claude agent layer (curated pipeline plus a locked-down, shadow-only Agent SDK Investigator) is built, tested and has had its first live runs (a few tens of cents, nothing scheduled yet); its output is unscored so far.** Nothing here trades. It collects data, records everything to an event log, and watches itself. What is left to finish Phase 0 is in [docs/phase0-checklist.md](docs/phase0-checklist.md).

- Design: [ARCHITECTURE.md](ARCHITECTURE.md) and the [diagram page](docs/architecture-map.html)
- Research behind it: [research/00-master-report.md](research/00-master-report.md) (reports 01 to 11 sit beside it)

> Personal research project. Not investment, legal or tax advice, and no performance claims. Anything that trades real money is behind your own manual approval.

## Quick start

```bash
uv sync
uv run pytest                  # 336 tests, offline, none call the real API
uv run getrich collect-binance # closed daily bars for BTCUSDT and ETHUSDT (public API, no key)
uv run getrich collect-news    # primary-source RSS (Fed, ECB, BoE, BoC, BoJ; SEC too if GETRICH_CONTACT is set in .env). Crypto outlets are excluded: docs/news-feed-terms.md
uv run getrich collect-webnews # open web headlines: GDELT raw files and Google News RSS, filtered to crypto, gold, FX and rates
uv run getrich watchdog        # run every health check once
uv run getrich status          # the status screen
uv run getrich doctor          # check this Mac against the hardening list
uv run getrich gate            # is Phase 0 finished? checks the event log for evidence
uv run getrich ack <item>      # record something only you can confirm (see the checklist)
uv run getrich ledger-verify   # verify the insight ledger's hash chain
uv run getrich validate-harness  # prove the evaluation harness can tell skill from luck
uv run getrich run-baselines   # baseline strategies on stored BTC/ETH data
uv run getrich derive-limits   # proposed risk limits derived from that history
uv run getrich run-phase2      # PI-Net v1 models vs the baselines on real data (about 6 minutes)
uv run getrich run-meta        # the pre-registered meta-label experiment
uv run getrich agents-extract --dry-run   # Haiku extraction: what it would do and cost (add ANTHROPIC_API_KEY to .env to run it)
uv run getrich agents-briefing --dry-run  # Sonnet briefing, flags and shadow views
uv run getrich investigate "What did the Fed just signal?" --dry-run   # locked-down research agent (Agent SDK): shows its lockdown config, starts nothing
uv run getrich agents-status   # Claude spend against the cap, ledger and scorecard
uv run getrich propose buy BTCUSDT --stop 64900   # PAPER order: runs the risk gate, prints its verdict, sends nothing
uv run getrich approve <order_id>                # you approve (typed yes); there is no auto-submit
uv run getrich positions       # paper equity, positions, realised result, halts  (add --venue testnet for the Binance testnet)
uv run getrich replay          # replay stored history through the real gate and paper broker; invariants plus comparison with the baselines (local only)
uv run getrich forecast-eval   # score cached Kronos / Chronos-2 / TimesFM forecasts against a random walk (weights are fetched explicitly: docs/forecast-models.md)
uv run getrich news-fetch      # daily GDELT news series (slow on purpose, cached, resumable)
uv run getrich news-study      # exploratory: do news features line up with forward BTC/ETH returns at all?
uv run getrich pinet-train --forecaster chronos2 --news gdelt --models lgbm --save   # EXPLORATORY: pick a forecaster/news channel, train, compare with baseline on identical rows
uv run getrich preregister && uv run getrich pinet-experiment   # the PRE-REGISTERED ablation (docs/preregistration-news-forecast.md)
uv run getrich kill            # kill switch: flatten everything, block new positions (unkill / unhalt to resume)
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
| Hash-chained insight ledger | `src/getrich/store/ledger.py` |
| Phase 0 exit gate and manual acknowledgements | `src/getrich/ops/gate.py` |
| Compute benchmark | `scripts/bench_compute.py`, `docs/benchmark-m4.md` |
| Evaluation harness: costs, purged CV and CPCV, Deflated Sharpe, triple-barrier labels, backtest, trend and HAR baselines, limit derivation, PI-Net v1 models | `src/getrich/eval/`, [docs/phase1-findings.md](docs/phase1-findings.md), [docs/phase2-findings.md](docs/phase2-findings.md) |

News rows keep two clocks, `published_at` (the source's claim) and `ingested_at` (ours). Backtests may only use `ingested_at`.
