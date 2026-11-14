# Phase 2 findings: PI-Net v1 on market and forecast channels

Date: 2026-11-14. **The Phase 2 gate was not met.** None of the three models beats the baselines after costs, and none shows detectable skill. Full tables: [phase2-results.md](phase2-results.md).

## Gate

| Gate item (ARCHITECTURE.md section 6) | Result |
|---|---|
| Beats the baselines net of 2x costs under CPCV | **No.** Best model Sharpe at 2x costs is -0.02 (linear). Trend baseline is 0.65, buy and hold 0.53 |
| Deflated Sharpe positive | **No.** 0.33 to 0.46 for the models, below 0.5 (the usual bar for confidence is 0.95) |
| Permutation test finds skill | **No.** p = 0.22 (linear), 0.63 (LightGBM), 0.38 (fusion net) |

## What was built and run

- **Dataset:** 4,194 candidate long trades on BTC and ETH, decisions from 2021-01-30 to 2026-11-03. Each is labelled by a triple-barrier rule (take-profit 2 sigma, stop 1 sigma, 10-day horizon) with assumed costs.
- **Channels:** market (19 features), forecast (3 features from the HAR volatility forecast) and context (3). No news or Claude channel yet, and no Chronos or TimesFM quantiles, because research found they do not beat a random walk on returns.
- **Models:** a ridge linear model, a two-head LightGBM, and the fusion network from the architecture (separate channel encoders, gated fusion with a missing-channel mask, p and expected-R heads, plus dense auxiliary targets). Hyperparameters were fixed in advance and not tuned on these results. Predictions average three seeds for the network.
- **Judging:** six-group combinatorial purged CV with a 6-day embargo (five complete out-of-sample paths), a strategy-level backtest at base and 2x costs, the Deflated Sharpe counting five trials, and shift-null permutation tests.

## Results

| | Sharpe (mean of 5 paths) | at 2x costs | Max drawdown | Excess R per trade taken | Null p-value |
|---|---:|---:|---:|---:|---:|
| linear | 0.24 | -0.02 | 52% | +0.037 | 0.22 |
| LightGBM | 0.09 | -0.25 | 58% | -0.026 | 0.63 |
| fusion net | 0.18 | -0.19 | 56% | +0.020 | 0.38 |
| trend baseline | 0.66 | 0.65 | 43% | n/a | n/a |
| buy and hold baseline | 0.53 | 0.53 | 76% | n/a | n/a |

## What this does and does not show

**It shows** that, with these features and this label design, there is no sign the models pick trades better than chance, and that they trade enough that doubling costs wipes out what little they earn. The trend baseline barely notices double costs because it trades about 3.5 times a year.

**It does not show** that no edge exists. The experiment's power is limited:

- Outcomes have a standard deviation of 1.4 R. Labels overlap (about 3 days on average), which leaves roughly 1,400 effectively independent trades by my rough count. That gives a standard error near 0.04 R, so an excess edge smaller than about 0.08 R would not be reliably detectable. The best model's +0.037 R is below that. This estimate is my own arithmetic and approximate.
- It is one crypto cycle and two highly correlated assets.
- Only one label geometry was tried.

So the honest reading is "no detectable edge of useful size", not "no edge".

## Why it is plausible

- **The setup starts behind.** Taking every candidate trade loses 0.083 R per trade at base costs (0.194 R at 2x). 64% of trades hit the 1-sigma stop (daily bars are noisy against a 3.2% stop), 32% reach the target and 4% time out. A model first has to overcome that, and the round-trip cost is 0.111 R because 30 bps is large against a 3.2% stop.
- **It matches the research.** Earlier tracks found return forecasting is near zero edge for most model types, and that the predictable part is volatility, which the sizing layer already uses.
- **The controls rule out a broken pipeline, not a missing edge.** All three models find a planted signal in the synthetic world and none finds one in noise (tests in `tests/test_eval_fusion.py`).

## Engineering notes

- PyTorch and LightGBM each bundle their own OpenMP runtime and abort a process that uses both on macOS. The usual workaround is documented as possibly giving wrong results, so each model runs in its own process (`pinet_worker.py`) and the parent loads neither.
- `torch` and `lightgbm` are in a default dependency group (`ml`), so a plain `uv sync` keeps them.
- 122 tests pass.

## What to do next (your decision)

Each new experiment adds trials, and the Deflated Sharpe penalises that, so these are worth choosing between rather than running all.

1. **Meta-label the trend baseline.** The research-supported design: the trend rule decides when to enter and the model only decides whether to take or skip each entry. Far fewer, more distinct samples, and it asks a narrower question.
2. **Try wider stops and a longer horizon.** Cost in R falls as the stop widens (about 0.055 R at a 2-sigma stop), and the stop is hit less by noise. One new label geometry, counted as new trials.
3. **Move on to Phase 3 without a profitable PI-Net.** Agents write briefings and event-risk flags into the ledger, which does not require the model to have an edge. The trend and volatility baseline stays as the strategy, and the ledger starts accumulating the data the Claude channel will need later.
4. **Stop here and reassess** whether a model-driven trading edge is realistic for this account size and these markets.

I would do 3 and 1 together: 3 needs time to accumulate data anyway, and 1 is the most credible next test of the modelling idea. That is my recommendation, not a finding, and the prior that either finds an edge is low.

## Reproduce

```bash
uv run getrich run-phase2 --null-fusion 20 --write   # about 6 minutes
uv run pytest
```
