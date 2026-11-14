# Phase 1 findings: the evaluation harness and the baselines

Date: 2026-11-14. Everything here is reproducible with the commands at the bottom. Tables with every number are in [phase1-baselines.md](phase1-baselines.md) and [risk-limits-proposal.md](risk-limits-proposal.md).

## Status against the Phase 1 gate

| Gate item | Status | Evidence |
|---|---|---|
| Harness rejects shuffled labels and finds a planted signal | **Done** | `getrich validate-harness` passes 4 controls (below) |
| Cost model, purged CV and CPCV, Deflated Sharpe, trend and HAR baselines | **Done** | 103 tests pass; baselines run on real data |
| Drawdown and loss limits derived from data | **Done** | [risk-limits-proposal.md](risk-limits-proposal.md) |
| You approve the limits | **Done, 2026-11-14: profile "minimal"** | `config/limits.toml`, `limits.approved` event in the log |

## 1. The harness works on synthetic worlds where the truth is known

| Control | Result |
|---|---|
| A real, weak signal is planted | Found: +0.217 R of skill, p = 0.016 against a null that keeps the outcomes' serial structure |
| Pure noise, 8 independent worlds | 0 of 8 mistaken for skill at the 5% level |
| The planted world with labels shuffled | Signal gone: -0.015 R, p = 0.51 |
| A deliberately leaky model on noise | Naive shuffled K-fold invents +0.69 R of skill. Purged CPCV finds +0.06 R |

The last row is the one that matters. Overlapping triple-barrier labels make an ordinary cross-validation produce impressive-looking skill from nothing, and the splitters here remove it. The leakage rules are also tested directly against their definitions, with a control showing a naive split would fail the same test.

## 2. What the baselines say about BTC and ETH, honestly

Sample: 2021-01-30 to 2026-11-13 (2,114 days). It starts there because the volatility forecaster needs a year of history. Costs are **assumed** (30 bps round trip), not measured. Spot, long-only, no leverage. No parameter was tuned on these results, but the choices (lookbacks, 20% volatility target, 10% no-trade band) were mine and the Deflated Sharpe counts only the 8 variants actually run, so treat it as generous.

| | Sharpe | CAGR | Max drawdown | Deflated Sharpe |
|---|---:|---:|---:|---:|
| BTC buy and hold | 0.49 | 12.6% | 76.6% | 0.80 |
| BTC trend (long/flat) | 0.63 | 18.3% | 47.1% | 0.88 |
| BTC trend, EWMA vol-scaled | 0.43 | 5.4% | 21.8% | 0.75 |
| BTC trend, HAR vol-scaled | 0.36 | 4.3% | 22.7% | 0.70 |
| ETH buy and hold | 0.45 | 6.0% | 79.3% | 0.77 |
| ETH trend (long/flat) | 0.54 | 15.7% | 51.6% | 0.83 |
| ETH trend, EWMA vol-scaled | 0.45 | 5.5% | 19.4% | 0.77 |
| ETH trend, HAR vol-scaled | 0.31 | 3.6% | 18.8% | 0.66 |

What I read from it:

1. **No strategy clears the bar.** Deflated Sharpe is the probability the true Sharpe is above zero after accounting for the 8 variants tried. The best is 0.88, below the usual 0.95. The evidence that trend beats chance is weak, and buy and hold is not distinguishable from zero either.
2. **The most robust-looking effect is smaller drawdowns, not higher returns.** Trend cut BTC's maximum drawdown from 77% to 47% and ETH's from 79% to 52%, and lost less in 2022 (BTC -14% against -64%). That is still a one-cycle observation.
3. **Volatility forecasting works, and it did not help the strategy.** HAR forecasts tomorrow's volatility clearly better than EWMA or yesterday's value (BTC QLIKE loss 0.415 against 0.463 and 0.806; ETH 0.395, 0.452, 0.715). That matches the earlier research finding that volatility is the predictable part. But scaling positions with the HAR forecast gave a lower Sharpe than EWMA scaling, because it traded more (9.5 turns a year against 2.2) and paid 1.4% a year in costs. At double costs its BTC Sharpe falls from 0.36 to 0.26.
4. **Volatility targeting at 20% leaves the account mostly in cash.** Average exposure was 25% in BTC and 16% in ETH, so returns are 4-5% a year. On a $400 account, my arithmetic puts that at roughly $20 a year before any other costs. A spot account cannot lever up to compensate, so a pure baseline cannot be expected to do more than this.
5. **Recent years were negative for every long-only variant.** BTC trend lost 5% in 2025 and 11% so far in 2026, against -6% and -22% for buy and hold.

## 3. The risk limits proposal

See [risk-limits-proposal.md](risk-limits-proposal.md). Two findings drive it:

- **A halt cannot stop a gap.** The worst 24-hour fall in the data was 46-48% (BTC and ETH, ending 2020-03-13). At a 25% exposure cap that is a 12% loss, and 17.9% with a 1.5x margin, which is larger than the 15% drawdown halt the same profile proposes. So the exposure cap is the real protection, and I added a rule: a profile is coherent only if one repeat of the worst fall (with margin) fits inside its own drawdown halt.
- **By that rule the largest coherent profile is "minimal":** 20% of equity in crypto at once, an account drawdown halt of 15%, and a daily loss halt of 2.5%. The 25%, 50% and 100% profiles all fail the rule.

You approved "minimal" on 2026-11-14. The choice among the four profiles was yours. I recommend the one the rule picks because nothing yet shows the system has an edge, and a profile can only be raised later by a written rule after live results exist. That is a research recommendation, not personal financial advice.

## 4. What Phase 1 does not show

- It says nothing about the PI-Net, agents or any model. It only builds the instrument that will judge them.
- The strategy statistics describe one crypto cycle. The limits use bootstrapped paths from that cycle, so they understate the risk of paths unlike any in the sample.
- The 24-hour fall statistic includes March 2020, which is before the strategy sample, so the gap rule is stricter than the drawdown statistics.
- The Deflated Sharpe and Probabilistic Sharpe formulas are implemented from my background knowledge and tested against hand computations and properties, not against the original papers.
- About 32 hours of hourly bars are missing from each symbol (probably exchange maintenance), which removes a few days from the volatility forecasts.
- Costs are assumptions until micro-live trading measures them. Everything is shown at 2x costs as well.

## Reproduce

```bash
uv run getrich validate-harness      # the four controls
uv run getrich run-baselines         # the baseline table
uv run getrich derive-limits --write # the limits proposal, baseline tables and proposed TOML
uv run getrich limits-approve --profile minimal   # only when you approve
```
