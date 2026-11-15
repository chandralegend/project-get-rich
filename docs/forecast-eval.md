# Foundation forecaster evaluation

Each model forecasts BTC and ETH cumulative log returns at 1, 5 and 20 days from every origin day, using only data up to that day. Scores are against a zero-drift random walk with the same volatility scale (positive skill = better than the random walk). `post_release` keeps origins on or after the model's public release date, which it cannot have seen in pretraining; `all` is the full history, where contamination could only inflate results. See `src/getrich/forecast/evaluate.py` for definitions.

## chronos2

**Verdict: no skill versus a random walk after release.** Origins cached: BTCUSDT 1999, ETHUSDT 1999.

| Window | h | n | Skill | Location skill | IC (95% CI) | Hit / up rate | Cover 80% / 40% | DM p |
|---|---:|---:|---:|---:|---|---|---|---:|
| all | 1 | 3996 | -0.044 | -0.038 | -0.020 (-0.05, +0.01) | 48.6% / 50.1% | 82% / 45% | 0.000 |
| all | 5 | 3988 | -0.009 | -0.019 | -0.024 (-0.08, +0.02) | 49.0% / 50.6% | 78% / 43% | 0.144 |
| all | 20 | 3958 | -0.016 | -0.037 | -0.064 (-0.15, +0.02) | 47.7% / 48.9% | 76% / 41% | 0.208 |
| post_release | 1 | 780 | -0.034 | -0.036 | -0.051 (-0.12, +0.01) | 46.7% / 49.0% | 83% / 47% | 0.001 |
| post_release | 5 | 772 | -0.019 | -0.032 | -0.069 (-0.20, +0.06) | 49.9% / 42.4% | 81% / 44% | 0.140 |
| post_release | 20 | 742 | -0.020 | -0.069 | -0.222 (-0.45, +0.00) | 42.3% / 45.3% | 74% / 41% | 0.501 |

## kronos_small

**Verdict: no skill versus a random walk after release.** Origins cached: BTCUSDT 470, ETHUSDT 470.

| Window | h | n | Skill | Location skill | IC (95% CI) | Hit / up rate | Cover 80% / 40% | DM p |
|---|---:|---:|---:|---:|---|---|---|---:|
| all | 1 | 938 | -0.325 | -0.297 | +0.010 (-0.05, +0.08) | 48.0% / 49.5% | 63% / 30% | 0.000 |
| all | 5 | 930 | -0.619 | -0.625 | +0.003 (-0.11, +0.11) | 51.6% / 43.3% | 57% / 29% | 0.000 |
| all | 20 | 900 | -0.746 | -0.790 | +0.077 (-0.13, +0.27) | 53.3% / 43.2% | 45% / 21% | 0.000 |
| post_release | 1 | 938 | -0.325 | -0.297 | +0.010 (-0.05, +0.08) | 48.0% / 49.5% | 63% / 30% | 0.000 |
| post_release | 5 | 930 | -0.619 | -0.625 | +0.003 (-0.11, +0.11) | 51.6% / 43.3% | 57% / 29% | 0.000 |
| post_release | 20 | 900 | -0.746 | -0.790 | +0.077 (-0.13, +0.27) | 53.3% / 43.2% | 45% / 21% | 0.000 |

## timesfm25

**Verdict: no skill versus a random walk after release.** Origins cached: BTCUSDT 1999, ETHUSDT 1999.

| Window | h | n | Skill | Location skill | IC (95% CI) | Hit / up rate | Cover 80% / 40% | DM p |
|---|---:|---:|---:|---:|---|---|---|---:|
| all | 1 | 3996 | -0.047 | -0.019 | -0.041 (-0.07, -0.01) | 48.4% / 50.1% | 89% / 56% | 0.000 |
| all | 5 | 3988 | -0.018 | -0.020 | -0.060 (-0.11, -0.02) | 47.3% / 50.6% | 83% / 47% | 0.001 |
| all | 20 | 3958 | -0.040 | -0.051 | -0.100 (-0.19, -0.00) | 46.8% / 48.9% | 80% / 45% | 0.016 |
| post_release | 1 | 850 | -0.037 | -0.012 | +0.008 (-0.06, +0.08) | 49.6% / 48.9% | 89% / 55% | 0.000 |
| post_release | 5 | 842 | -0.022 | -0.019 | -0.007 (-0.12, +0.09) | 49.4% / 42.0% | 85% / 49% | 0.032 |
| post_release | 20 | 812 | -0.013 | -0.050 | +0.067 (-0.16, +0.28) | 56.8% / 42.9% | 81% / 47% | 0.718 |

## How to read this

- Skill and IC near zero, or intervals that straddle zero, mean no demonstrated edge. Coverage far from 80% / 40% means the model's uncertainty is wrong and it would need recalibration before use.
- Overlapping horizons make daily origins strongly dependent, so the effective sample is roughly n / h. The post-release window is short; a null result there is weak evidence of no skill, a positive one needs forward confirmation.
- A model is only wired into a trading model if it shows skill here on post-release data.
