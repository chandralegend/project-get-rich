# Hourly mean-reversion day trading, long and short, with leverage (pre-registered)

Pre-registration: `docs/preregistration-futures-reversion.md`, SHA-256 `a67e9ee47c1d068f...` (matches the hash logged before the run). Window 2020-01-03 to 2026-11-15 on hourly BTCUSDT and ETHUSDT bars; start equity $500; what-if limits (30% drawdown halt, 5.5% daily halt, 2% risk per trade; NOT approved). Costs 10 + 5 bps per side (2x also run); funding ASSUMED 0.01% per 8 hours (3x also run). Deflated Sharpe counts 45 trials.

| | Trades | Win rate | Avg R | Total | CAGR | Sharpe | at 2x costs | 2x + 3x funding | Max DD | Deflated Sharpe | Avg exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H0: long only, up to 3x | 1073 | 45% | -0.19 | -98.8% | -47.5% | -1.97 | -1.98 | -2.01 | 98.9% | 0.000 | 20% |
| H1: long and short, no leverage | 1140 | 42% | -0.23 | -99.0% | -48.9% | -2.47 | -2.67 | -2.67 | 99.1% | 0.000 | 18% |
| H2: long and short, up to 3x (primary) | 1130 | 44% | -0.21 | -99.3% | -51.0% | -2.22 | -2.63 | -2.53 | 99.3% | 0.000 | 21% |

## What each part contributed (2x costs, dollars on a $500 start)

| | Long trades P&L | Short trades P&L | Fees (base) | Net funding paid (base) | Halt tripped | Liquidated | Violations |
|---|---:|---:|---:|---:|---|---|---:|
| H0 | -475 | +0 | 211 | +16.9 | yes | no | 0 |
| H1 | -146 | -349 | 144 | -2.9 | yes | no | 0 |
| H2 | -146 | -349 | 158 | -3.2 | yes | no | 0 |

The 30% drawdown halt trips, blocks new entries for 14 days, then the owner is assumed to review and reset it (peak restarts at the then-current equity). Max DD above is the true one from the all-time peak. Halts (base costs): H0 13 (2020-08-12, 2021-05-19, 2022-01-21, 2022-06-13, 2022-09-19, 2023-03-09, 2024-04-02, 2024-08-04, ...); H1 14 (2020-03-12, 2020-06-25, 2020-10-21, 2020-12-21, 2021-03-30, 2021-06-16, 2021-09-20, 2022-02-04, ...); H2 15 (2020-02-26, 2020-04-23, 2020-07-27, 2020-11-20, 2021-01-03, 2021-03-31, 2021-06-16, 2021-09-20, ...).

## By calendar year (base costs)

| Year | H0 | H1 | H2 |
|---|---:|---:|---:|
| 2020 | -30.1% | -74.5% | -79.3% |
| 2021 | -33.7% | -68.5% | -68.6% |
| 2022 | -61.1% | -62.9% | -66.4% |
| 2023 | -34.2% | -44.8% | -64.6% |
| 2024 | -55.4% | -39.6% | -4.4% |
| 2025 | -42.5% | +0.0% | +0.0% |
| 2026 | -61.0% | +0.0% | +0.0% |

## Gate rejections of H2 signals (base costs)

quantity: 3294, halt_latch: 588, daily_loss_halt: 251, stop_distance: 2

Signals seen: {'BTCUSDT': 2635, 'ETHUSDT': 2630}.

## Pre-registered criteria for H2

- FAIL: Sharpe at 2x costs at least 1.0
- FAIL: Deflated Sharpe at least 0.90
- FAIL: true max drawdown at most 40%
- FAIL: Sharpe at 2x costs positive in both halves
- FAIL: Sharpe positive at 2x costs with 3x funding
- PASS: at least 150 trades
- FAIL: short trades profitable at 2x costs
- PASS: no violations, no liquidation

**Verdict: H2 NOT SHOWN.**

Caveats: one in-sample path; funding and maintenance margin are assumptions; perpetual basis ignored; fills at the close or the stop level with no queue or partial fills; a gap through a stop is the loss leverage multiplies and no stop can prevent.
