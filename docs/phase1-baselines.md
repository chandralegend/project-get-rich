# Phase 1 baselines on real data

Costs: 10 bps fee + 5 bps slippage per side (30 bps round trip), both ASSUMED, plus a 2x stress. Spot, long-only, no leverage, daily bars, no-trade band 10%, volatility target 20%.

## Strategy results (net of costs, common sample per asset)

| Asset | Strategy | Days | CAGR | Vol | Sharpe | Sharpe at 2x costs | Max DD | Worst day | Exposure | Turnover/yr | Cost drag/yr | Deflated Sharpe |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | buy_and_hold | 2114 | 12.6% | 55.8% | 0.49 | 0.49 | 76.6% | -15.4% | 100% | 0.2 | 0.03% | 0.80 |
| BTCUSDT | trend | 2114 | 18.3% | 38.7% | 0.63 | 0.61 | 47.1% | -12.4% | 58% | 3.5 | 0.52% | 0.88 |
| BTCUSDT | trend_ewma | 2114 | 5.4% | 14.7% | 0.43 | 0.41 | 21.8% | -6.9% | 25% | 2.2 | 0.33% | 0.75 |
| BTCUSDT | trend_har | 2114 | 4.3% | 14.8% | 0.36 | 0.26 | 22.7% | -6.6% | 25% | 9.5 | 1.42% | 0.70 |
| ETHUSDT | buy_and_hold | 2114 | 6.0% | 74.7% | 0.45 | 0.45 | 79.3% | -27.7% | 100% | 0.2 | 0.03% | 0.77 |
| ETHUSDT | trend | 2114 | 15.7% | 51.3% | 0.54 | 0.53 | 51.6% | -27.7% | 53% | 3.6 | 0.54% | 0.83 |
| ETHUSDT | trend_ewma | 2114 | 5.5% | 14.0% | 0.45 | 0.44 | 19.4% | -6.7% | 16% | 1.3 | 0.20% | 0.77 |
| ETHUSDT | trend_har | 2114 | 3.6% | 14.7% | 0.31 | 0.26 | 18.8% | -4.7% | 18% | 4.8 | 0.72% | 0.66 |

Deflated Sharpe counts 8 trials (every asset and strategy above). It is the probability the true Sharpe is above zero after that many tries.

## Volatility forecast quality (QLIKE loss, lower is better)

| Asset | Forecaster | QLIKE | Days |
|---|---|---:|---:|
| BTCUSDT | HAR-RV | 0.4148 | 2106 |
| BTCUSDT | EWMA 0.94 | 0.4628 | 2106 |
| BTCUSDT | yesterday's RV | 0.8057 | 2106 |
| ETHUSDT | HAR-RV | 0.3950 | 2106 |
| ETHUSDT | EWMA 0.94 | 0.4522 | 2106 |
| ETHUSDT | yesterday's RV | 0.7146 | 2106 |

## Net return by calendar year

| Asset | Strategy | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | buy_and_hold | 35% | -64% | 156% | 121% | -6% | -22% |
| BTCUSDT | trend | 18% | -14% | 61% | 91% | -5% | -11% |
| BTCUSDT | trend_ewma | 1% | -7% | 18% | 34% | -2% | -7% |
| BTCUSDT | trend_har | -1% | -6% | 15% | 27% | -1% | -5% |
| ETHUSDT | buy_and_hold | 166% | -67% | 91% | 46% | -11% | -35% |
| ETHUSDT | trend | 144% | -27% | 27% | 20% | 3% | -16% |
| ETHUSDT | trend_ewma | 30% | -7% | 9% | 11% | 1% | -8% |
| ETHUSDT | trend_har | 22% | -8% | 7% | 6% | 5% | -7% |
