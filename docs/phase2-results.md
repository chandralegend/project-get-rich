# Phase 2 results: PI-Net v1 on market and forecast channels

Dataset: 4194 candidate long trades (BTCUSDT, ETHUSDT), decisions from 2021-01-30 to 2026-11-03. Triple-barrier: take-profit 2 sigma, stop 1 sigma, 10-day horizon. Costs 10+5 bps per side (assumed) and 2x.
Taking every candidate trade averages -0.083 R at base costs and -0.194 R at 2x; 35% of trades end with positive net R; mean round-trip cost 0.111 R.

Evaluation: 6-group combinatorial purged CV (2 test groups), 6-day embargo, 5 complete out-of-sample paths. Strategy mapping: hold each asset long while the model's expected net R is positive. Mean across paths, with the worst and best path.

## Models against the baselines (portfolio of BTC and ETH sleeves, net of costs)

| | Sharpe (mean, min to max) | Sharpe at 2x costs | CAGR | Max DD | Time long | Excess R per trade taken | at 2x | Deflated Sharpe | Null p-value |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| model: linear | 0.24 (-0.05 to 0.45) | -0.02 | 2.4% | 52.1% | 38% | +0.037 | +0.040 | 0.46 | 0.218 (100 draws) |
| model: lgbm | 0.09 (-0.22 to 0.34) | -0.25 | -2.1% | 58.4% | 35% | -0.026 | -0.025 | 0.33 | 0.634 (40 draws) |
| model: fusion | 0.18 (-0.15 to 0.51) | -0.19 | 0.0% | 56.2% | 39% | +0.020 | +0.021 | 0.40 | 0.381 (20 draws) |
| baseline: buy_and_hold | 0.53 | 0.53 | 14.6% | 76.3% | n/a | n/a | n/a | 0.72 | n/a |
| baseline: trend | 0.66 | 0.65 | 20.9% | 42.7% | n/a | n/a | n/a | 0.81 | n/a |

Deflated Sharpe counts 5 trials (the three models and the two baselines). 'Excess R per trade taken' is the harness score: mean net R of trades the model takes minus the mean of taking every candidate; zero means no skill.
