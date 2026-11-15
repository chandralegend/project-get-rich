# Wider-universe trend and momentum study (pre-registered)

Pre-registration: `docs/preregistration-portfolio.md`, SHA-256 `8a9d00b624326ca0...` (matches the hash logged before the run).
16 coins (about 16 eligible on an average day), 2021-01-30 to 2026-11-14, halves split at 2023-12-23. Deflated Sharpe counts 27 trials. Survivorship bias flatters every long-only row; it cannot be removed with free data.

| | Sharpe | at 2x costs | CAGR | Max DD | Avg exposure | Half 1 / half 2 at 2x | Deflated Sharpe | Gain vs hold-all, vs BTC (2x) | Shows value? |
|---|---:|---:|---:|---:|---:|---|---:|---|---|
| S0 equal-weight hold | 0.44 | 0.44 | 3.1% | 86.6% | 110% | 0.59 / 0.26 | 0.62 | benchmark | n/a |
| S1 trend, equal weight | 0.47 | 0.46 | 11.2% | 65.6% | 41% | 0.78 / 0.03 | 0.64 | +0.02, -0.01 | no (gain_vs_both, dsr, drawdown failed) |
| S2 trend, risk parity | 0.50 | 0.50 | 12.8% | 53.6% | 39% | 0.75 / 0.14 | 0.67 | +0.05, +0.02 | no (gain_vs_both, dsr, drawdown failed) |
| S3 trend, volatility target | 0.52 | 0.51 | 9.5% | 33.2% | 26% | 0.88 / 0.29 | 0.69 | +0.07, +0.04 | no (gain_vs_both, dsr failed) |
| S4 momentum, top 5 | 0.42 | 0.35 | 6.6% | 84.1% | 68% | 0.68 / -0.05 | 0.60 | -0.09, -0.12 | no (gain_vs_both, dsr, both_halves_positive, drawdown failed) |
| reference: BTC buy and hold | 0.47 | 0.47 | 11.4% | 76.6% | 100% | | | | |

## Calendar years (base costs, full exposure)

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| S0 equal-weight hold | 155.0% | -72.3% | 103.1% | 115.4% | -34.3% | -41.3% |
| S1 trend, equal weight | 102.9% | -6.1% | 17.6% | 38.5% | -30.2% | -14.6% |
| S2 trend, risk parity | 91.6% | -9.4% | 17.5% | 31.0% | -15.9% | -10.6% |
| S3 trend, volatility target | 33.6% | -3.1% | 15.4% | 46.2% | -9.7% | -14.2% |
| S4 momentum, top 5 | 157.0% | -35.2% | 22.0% | 37.3% | -30.1% | -25.7% |

## Bootstrap of the Sharpe difference at 2x costs (95% interval; share of draws where the strategy is ahead)

| | vs equal-weight hold | vs BTC buy and hold |
|---|---|---|
| S1 trend, equal weight | -0.53 to +0.58 (51%) | -0.78 to +0.77 (50%) |
| S2 trend, risk parity | -0.49 to +0.60 (56%) | -0.69 to +0.73 (53%) |
| S3 trend, volatility target | -0.47 to +0.56 (59%) | -0.69 to +0.77 (52%) |
| S4 momentum, top 5 | -0.59 to +0.35 (32%) | -0.92 to +0.62 (37%) |

## What it means in dollars on $500 under the approved limits (exposure capped at 20% of equity)

| | CAGR at the cap | Dollars a year on $500 | Max drawdown at the cap |
|---|---:|---:|---:|
| S0 equal-weight hold | 6.0% | $30 | 26.0% |
| S1 trend, equal weight | 4.1% | $21 | 15.3% |
| S2 trend, risk parity | 3.8% | $19 | 11.1% |
| S3 trend, volatility target | 2.2% | $11 | 6.9% |
| S4 momentum, top 5 | 4.7% | $23 | 25.0% |

Criteria (all required, for each of S1 to S4): Sharpe at 2x costs at least 0.10 above BOTH hold-all and BTC buy and hold, Deflated Sharpe at least 0.9, positive Sharpe at 2x costs in both halves, maximum drawdown at most 40% at full exposure.

Caveats: the 5% no-trade band lets held weights drift, so average exposure can exceed the target (S0 averages above 100%), which slightly flatters S0 and is the reason it is a conservative benchmark. Survivorship bias flatters all rows. One crypto cycle, so differences under about 0.3 Sharpe are inside the noise (see the bootstrap intervals).
