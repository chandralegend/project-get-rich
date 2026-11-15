# News + forecaster experiment results (pre-registered)

Pre-registration: `docs/preregistration-news-forecast.md`, SHA-256 `4a18b24e19de9d52...` (matches the hash logged before the run).
Forecaster channel: chronos2. News channel: gdelt. 2078 trend-entry samples (2021-05-26 to 2026-10-25); per asset {'BTCUSDT': 1071, 'ETHUSDT': 1007}. Triple-barrier 4 sigma / 2 sigma / 20 days. Taking every entry averages -0.063 R at base costs and -0.122 R at 2x; 35% end positive.
Deflated Sharpe counts 35 trials (the cumulative registry plus this experiment's).

| | channels | Sharpe (mean, min to max) | at 2x costs | gain vs A at 2x | gain vs primary alone at 2x | CAGR | Max DD | Excess R per entry | Deflated Sharpe | Null p | Shows value? |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| linear:A | baseline | 0.37 (0.13 to 0.57) | 0.23 | +0.00 | -0.34 | 6.3% | 31.3% | -0.021 | 0.48 | 0.535 (100 draws) | reference |
| linear:B | +foundation | 0.09 (-0.08 to 0.30) | -0.07 | -0.30 | -0.64 | -0.1% | 33.8% | -0.056 | 0.25 | 0.683 (100 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| linear:C | +news | 0.26 (0.14 to 0.47) | 0.02 | -0.21 | -0.55 | 3.5% | 34.7% | -0.091 | 0.38 | 0.822 (100 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| linear:D | +foundation+news | 0.09 (-0.21 to 0.30) | -0.13 | -0.36 | -0.71 | -0.3% | 35.7% | -0.131 | 0.26 | 0.921 (100 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| lgbm:A | baseline | 0.53 (0.34 to 0.67) | 0.35 | +0.00 | -0.22 | 9.0% | 25.4% | -0.004 | 0.62 | 0.585 (40 draws) | reference |
| lgbm:B | +foundation | 0.67 (0.43 to 0.99) | 0.45 | +0.10 | -0.12 | 11.9% | 21.8% | +0.067 | 0.72 | 0.366 (40 draws) | no (gain_vs_primary_alone, p_value, dsr failed) |
| lgbm:C | +news | 0.37 (-0.15 to 0.70) | 0.10 | -0.26 | -0.48 | 5.9% | 24.8% | -0.081 | 0.49 | 0.683 (40 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| lgbm:D | +foundation+news | 0.53 (0.33 to 0.88) | 0.26 | -0.09 | -0.31 | 8.7% | 22.2% | +0.002 | 0.61 | 0.561 (40 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| fusion:A | baseline | 0.36 (0.23 to 0.71) | 0.19 | +0.00 | -0.39 | 5.7% | 24.3% | -0.054 | 0.47 | 0.714 (20 draws) | reference |
| fusion:B | +foundation | 0.06 (-0.13 to 0.27) | -0.15 | -0.33 | -0.72 | -0.2% | 28.7% | -0.055 | 0.24 | 0.810 (20 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| fusion:C | +news | 0.31 (0.18 to 0.54) | 0.04 | -0.15 | -0.54 | 4.6% | 29.0% | -0.123 | 0.42 | 0.857 (20 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| fusion:D | +foundation+news | 0.14 (-0.14 to 0.33) | -0.12 | -0.31 | -0.70 | 1.0% | 31.0% | -0.129 | 0.29 | 0.905 (20 draws) | no (gain_vs_baseline_variant, gain_vs_primary_alone, p_value, dsr failed) |
| baseline: buy_and_hold | | 0.41 | 0.41 | n/a | n/a | 6.7% | 76.3% | n/a | 0.51 | n/a | n/a |
| baseline: trend | | 0.50 | 0.48 | n/a | n/a | 12.1% | 42.7% | n/a | 0.59 | n/a | n/a |
| baseline: primary_alone | | 0.59 | 0.58 | n/a | n/a | 16.5% | 41.0% | n/a | 0.67 | n/a | n/a |

Criteria (all required, for each of B, C, D): Sharpe at 2x costs at least 0.10 above BOTH the same model on A and the primary rule alone, shift-null p below 0.05, Deflated Sharpe at least 0.9.
