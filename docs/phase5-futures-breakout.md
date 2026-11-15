# Hourly breakout day trading, long and short, with leverage (pre-registered)

Pre-registration: `docs/preregistration-futures-breakout.md`, SHA-256 `dcb0969fb45e3924...` (matches the hash logged before the run). Window 2020-01-02 to 2026-11-15 on hourly BTCUSDT and ETHUSDT bars; start equity $500; what-if limits (30% drawdown halt, 5.5% daily halt, 2% risk per trade; NOT approved). Costs 10 + 5 bps per side (2x also run); funding ASSUMED 0.01% per 8 hours (3x also run). Deflated Sharpe counts 39 trials.

| | Trades | Win rate | Avg R | Total | CAGR | Sharpe | at 2x costs | 2x + 3x funding | Max DD | Deflated Sharpe | Avg exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F0: long only, up to 3x | 496 | 49% | +0.17 | +273.6% | 21.1% | 0.83 | 0.33 | 0.24 | 30.0% | 0.839 | 15% |
| F1: long and short, no leverage | 734 | 45% | +0.09 | +65.9% | 7.6% | 0.41 | 0.12 | 0.10 | 30.5% | 0.434 | 17% |
| F2: long and short, up to 3x (primary) | 215 | 45% | +0.11 | +44.3% | 5.5% | 0.37 | 0.09 | 0.10 | 27.7% | 0.388 | 7% |

## What each part contributed (2x costs, dollars on a $500 start)

| | Long trades P&L | Short trades P&L | Fees (base) | Net funding paid (base) | Halt tripped | Liquidated | Violations |
|---|---:|---:|---:|---:|---|---|---:|
| F0 | +263 | +0 | 992 | +174.7 | yes | no | 0 |
| F1 | +104 | -71 | 561 | +26.9 | yes | no | 0 |
| F2 | +118 | -100 | 240 | +9.9 | yes | no | 0 |

The drawdown halt latches until the owner resets it (`unhalt`), and this replay never resets it, so after it trips a variant takes no new trades for the rest of the window. Halt tripped on (base costs): F0 2022-01-09, F1 2021-11-15, F2 2020-07-14. Years after that date show 0.0% because nothing was traded, not because the rule was tested and found flat.

## By calendar year (base costs)

| Year | F0 | F1 | F2 |
|---|---:|---:|---:|
| 2020 | +212.9% | +47.8% | +44.3% |
| 2021 | +27.9% | +12.2% | +0.0% |
| 2022 | -6.6% | +0.0% | +0.0% |
| 2023 | +0.0% | +0.0% | +0.0% |
| 2024 | +0.0% | +0.0% | +0.0% |
| 2025 | +0.0% | +0.0% | +0.0% |
| 2026 | +0.0% | +0.0% | +0.0% |

## Gate rejections of F2 signals (base costs)

halt_latch: 6862, daily_loss_halt: 3, stop_distance: 2

Signals seen: {'BTCUSDT': 3505, 'ETHUSDT': 3577}.

## Pre-registered criteria for F2

- FAIL: Sharpe at 2x costs at least 1.0
- FAIL: Deflated Sharpe at least 0.90
- FAIL: max drawdown at most 30% and the halt never trips
- FAIL: Sharpe at 2x costs positive in both halves
- PASS: Sharpe positive at 2x costs with 3x funding
- PASS: at least 150 trades
- FAIL: short trades profitable at 2x costs
- PASS: no violations, no liquidation

**Verdict: F2 NOT SHOWN.**

Caveats: one in-sample path; funding and maintenance margin are assumptions; perpetual basis ignored; fills at the close or the stop level with no queue or partial fills; a gap through a stop is the loss leverage multiplies and no stop can prevent.
