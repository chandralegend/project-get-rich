# Meta-label experiment results (pre-registered)

Pre-registration: `docs/preregistration-meta-label.md`, SHA-256 `acf45952f9f5f88a...` (matches the hash logged before the run).
2300 trend-entry samples (2021-01-30 to 2026-10-24), triple-barrier 4 sigma / 2 sigma / 20 days. Taking every entry averages -0.052 R at base costs and -0.109 R at 2x; 35% end positive.
Deflated Sharpe counts 17 trials (the cumulative registry plus this experiment's four).

| | Sharpe (mean, min to max) | at 2x costs | gain vs primary alone at 2x | CAGR | Max DD | Excess R per entry taken | Deflated Sharpe | Null p | Shows value? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| meta:linear | 0.28 (-0.19 to 0.56) | 0.10 | -0.56 | 4.4% | 29.8% | -0.080 | 0.46 | 0.743 (100 draws) | no (sharpe_gain, p_value, dsr failed) |
| meta:lgbm | 0.65 (0.33 to 0.86) | 0.47 | -0.20 | 11.4% | 28.2% | +0.037 | 0.75 | 0.390 (40 draws) | no (sharpe_gain, p_value, dsr failed) |
| meta:fusion | 0.10 (-0.09 to 0.33) | -0.10 | -0.76 | 0.1% | 38.7% | -0.108 | 0.29 | 0.952 (20 draws) | no (sharpe_gain, p_value, dsr failed) |
| baseline: buy_and_hold | 0.54 | 0.54 | n/a | 15.4% | 76.3% | n/a | 0.68 | n/a | n/a |
| baseline: trend | 0.68 | 0.67 | n/a | 21.8% | 42.7% | n/a | 0.79 | n/a | n/a |
| baseline: primary_alone | 0.68 | 0.66 | n/a | 22.4% | 44.2% | n/a | 0.79 | n/a | n/a |

Criteria (all required): Sharpe at 2x costs at least 0.10 above the primary rule alone, shift-null p below 0.05, Deflated Sharpe at least 0.9.
