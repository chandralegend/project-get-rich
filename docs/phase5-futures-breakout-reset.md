# Hourly breakout day trading with the drawdown halt reset after a cool-off (pre-registered)

Pre-registration: `docs/preregistration-futures-reset.md`, SHA-256 `41b99b0e3fba728e...` (matches the hash logged before the run). Window 2020-01-02 to 2026-11-15 on hourly BTCUSDT and ETHUSDT bars; start equity $500; what-if limits (30% drawdown halt, 5.5% daily halt, 2% risk per trade; NOT approved). Costs 10 + 5 bps per side (2x also run); funding ASSUMED 0.01% per 8 hours (3x also run). Deflated Sharpe counts 42 trials.

| | Trades | Win rate | Avg R | Total | CAGR | Sharpe | at 2x costs | 2x + 3x funding | Max DD | Deflated Sharpe | Avg exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| G0: long only, up to 3x | 1473 | 44% | +0.03 | -13.5% | -2.1% | 0.18 | -0.63 | -0.74 | 83.8% | 0.109 | 56% |
| G1: long and short, no leverage | 2319 | 40% | -0.03 | -88.1% | -26.6% | -0.52 | -1.18 | -1.37 | 95.5% | 0.001 | 62% |
| G2: long and short, up to 3x (primary) | 2489 | 40% | -0.04 | -96.3% | -38.1% | -0.52 | -1.07 | -1.13 | 98.9% | 0.001 | 88% |

## What each part contributed (2x costs, dollars on a $500 start)

| | Long trades P&L | Short trades P&L | Fees (base) | Net funding paid (base) | Halt tripped | Liquidated | Violations |
|---|---:|---:|---:|---:|---|---|---:|
| G0 | -309 | +0 | 3108 | +516.1 | yes | no | 0 |
| G1 | +89 | -561 | 1111 | +26.0 | yes | no | 0 |
| G2 | +202 | -673 | 1472 | +43.6 | yes | no | 0 |

The 30% drawdown halt trips, blocks new entries for 14 days, then the owner is assumed to review and reset it (peak restarts at the then-current equity). Max DD above is the true one from the all-time peak. Halts (base costs): G0 10 (2022-01-09, 2022-05-22, 2022-10-03, 2023-07-02, 2024-04-01, 2024-08-22, 2025-02-14, 2026-02-09, ...); G1 11 (2021-11-15, 2022-03-11, 2022-05-20, 2022-09-28, 2023-06-10, 2023-11-21, 2024-06-19, 2025-02-22, ...); G2 23 (2020-07-14, 2021-11-14, 2022-01-04, 2022-04-20, 2022-05-24, 2022-09-01, 2022-09-30, 2022-12-27, ...).

## By calendar year (base costs)

| Year | G0 | G1 | G2 |
|---|---:|---:|---:|
| 2020 | +212.9% | +47.8% | +62.6% |
| 2021 | +27.9% | +9.9% | +22.1% |
| 2022 | -37.2% | -54.4% | -69.8% |
| 2023 | -8.8% | -46.8% | -53.3% |
| 2024 | +1.1% | +0.2% | -39.5% |
| 2025 | -35.3% | -53.3% | -54.8% |
| 2026 | -42.3% | -35.4% | -51.6% |

## Gate rejections of G2 signals (base costs)

halt_latch: 883, daily_loss_halt: 57, stop_distance: 2

Signals seen: {'BTCUSDT': 1699, 'ETHUSDT': 1733}.

## Pre-registered criteria for G2

- FAIL: Sharpe at 2x costs at least 1.0
- FAIL: Deflated Sharpe at least 0.90
- FAIL: true max drawdown at most 40%
- FAIL: Sharpe at 2x costs positive in both halves
- FAIL: Sharpe positive at 2x costs with 3x funding
- PASS: at least 150 trades
- FAIL: short trades profitable at 2x costs
- PASS: no violations, no liquidation

**Verdict: G2 NOT SHOWN.**

Caveats: one in-sample path; funding and maintenance margin are assumptions; perpetual basis ignored; fills at the close or the stop level with no queue or partial fills; a gap through a stop is the loss leverage multiplies and no stop can prevent.
