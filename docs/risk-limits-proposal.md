# Risk limits proposal (for your approval)

Derived on 2114 days of baseline trend-strategy returns (2021-01-30 to 2026-11-13), equal-weight BTC and ETH sleeves, net of assumed costs. These are rules applied to historical numbers. History is one crypto cycle: a worse path is possible, so treat every number as a floor on risk, not a ceiling.

## How each number is derived

- **Exposure cap**: the largest fraction of equity in crypto at once. It is the main risk knob, because a spot long-only account has no way to cut a position during a gap.
- **Account drawdown halt**: the 95th percentile of simulated one-year maximum drawdown (stationary bootstrap, 5,000 paths, 20-day average block), rounded up to the next 5%. Normal variance should rarely hit it.
- **Daily loss halt**: the loss of a day worse than 99.9% of historical days, rounded up to the next 0.5% (minimum 0.25%).
- **Worst 24-hour event**: the largest 24-hour fall in either asset (BTCUSDT 46.4% ending 2020-03-13, ETHUSDT 47.8% ending 2020-03-13), times a 1.5x margin, times the exposure cap. This is what one gap does to the account.

## Profiles

| | minimal | conservative | moderate | full |
|---|---:|---:|---:|---:|
| Exposure cap (share of equity in crypto) | 20% | 25% | 50% | 100% |
| Historical max drawdown, this strategy | 10.0% | 12.4% | 23.5% | 42.7% |
| 1-year max drawdown, median | 6.2% | 7.7% | 15.1% | 28.8% |
| 1-year max drawdown, 90th percentile | 10.5% | 12.9% | 24.9% | 45.3% |
| 1-year max drawdown, 95th percentile | 12.0% | 14.9% | 28.3% | 50.3% |
| 1-year max drawdown, 99th percentile | 15.5% | 19.1% | 35.4% | 60.4% |
| Worst historical day | 3.73% | 4.67% | 9.33% | 18.66% |
| Daily loss at the 99.9th percentile | 2.08% | 2.60% | 5.21% | 10.42% |
| Loss from worst 24-hour fall x 1.5 | 14.3% | 17.9% | 35.8% | 71.7% |
| **Proposed account drawdown halt** | **15%** | **15%** | **30%** | **55%** |
| Does a repeat of the worst 24-hour fall (x1.5) fit inside that halt? | yes | **no** | **no** | **no** |
| **Proposed daily loss halt** | **2.5%** | **3.0%** | **5.5%** | **10.5%** |

## Worst 24-hour falls in the data (hourly closes)

| Asset | Date (UTC) | Fall |
|---|---|---:|
| BTCUSDT | 2020-03-13 01:00 | 46.4% |
| BTCUSDT | 2021-01-11 15:00 | 20.4% |
| BTCUSDT | 2021-05-19 12:00 | 19.8% |
| BTCUSDT | 2022-06-14 01:00 | 19.1% |
| BTCUSDT | 2024-08-05 12:00 | 18.4% |
| ETHUSDT | 2020-03-13 01:00 | 47.8% |
| ETHUSDT | 2021-05-20 00:00 | 33.5% |
| ETHUSDT | 2021-01-11 16:00 | 25.7% |
| ETHUSDT | 2022-11-09 16:00 | 24.0% |
| ETHUSDT | 2024-08-05 12:00 | 23.8% |

## Recommended starting profile: minimal

Exposure cap 20%, account drawdown halt 15%, daily loss halt 2.5%. 
The rule: pick the largest profile whose worst-24-hour-fall loss (with margin) still fits inside its own drawdown halt. A halt cannot stop a gap, so a profile where one gap breaks the halt is not coherent, whatever its average behaviour. Nothing yet shows the system has an edge, so the profile can only be raised later by a written rule after live results exist. This is a research recommendation, not personal financial advice. Which profile you accept is your decision.
