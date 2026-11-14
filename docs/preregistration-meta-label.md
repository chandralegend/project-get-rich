# Pre-registration: meta-labelling the trend rule

Written 2026-11-14 BEFORE running the experiment. Its SHA-256 is logged as an `eval.preregistered` event at the time of running, so the file cannot be changed afterwards without the mismatch being visible. Nothing below may be changed after seeing results. Any change is a new experiment with new trials.

## Question

Does a model that decides whether to take or skip each entry signalled by the trend rule improve on the trend rule alone, after costs, on data it has not seen?

## Primary rule (not a model)

Go long an asset at a day's close when at least 2 of the 3 EMA-crossover votes (16/64, 32/128, 64/256) are bullish, i.e. `trend_votes >= 2/3`. This is the same trend signal used by the Phase 1 baselines.

## Samples

Every day on which the primary rule says long, for BTCUSDT and ETHUSDT, from the first day the volatility forecast exists (2021-01-30) to the last day with a resolved label. Rows overlap heavily; the splitters purge and embargo for that.

## Labels (fixed geometry)

Triple-barrier with take-profit 4 sigma, stop-loss 2 sigma, horizon 20 days, sigma the 20-day EWMA of daily returns, long only. Costs 10 + 5 bps per side (assumed), outcomes in R as in Phase 1 and 2. This is wider and slower than Phase 2 (2 / 1 / 10) because it matches trend-following timescales and cuts the cost drag in R. It was chosen once, before seeing any meta-label result, and is the only geometry tried.

## Models

The same three models and the same fixed hyperparameters as Phase 2: ridge linear, two-head LightGBM, fusion network (market, forecast and context channels). No tuning.

## Decision and strategy

Take an entry when the model's expected net R is above zero. Hold the asset while the primary rule is long AND the model takes it; otherwise cash. Equal-weight sleeves for BTC and ETH, 10% no-trade band, same backtest engine as before.

## Evaluation

6-group combinatorial purged CV with 2 test groups (5 out-of-sample paths), embargo 11 days (half the horizon plus one). Judged at base costs and at 2x costs. Permutation test: shift null on the harness score (excess net R of trades taken over taking every entry), 100 draws for the linear model, 40 for LightGBM, 20 for the fusion network.

## Comparators

1. The primary rule alone (take every entry), the thing the models filter.
2. The graded trend baseline and buy and hold from Phase 1 and 2.

## Trial accounting

Every model and comparator counts as a trial in the cumulative registry (`docs/trials.json`). The Deflated Sharpe uses the full registry, not just this experiment: 13 trials before this one, 4 added by it.

## Success criteria (all must hold)

A model "shows value" only if, for that model:
1. its mean path Sharpe at 2x costs exceeds the primary rule alone at 2x costs by at least 0.10, AND
2. its shift-null permutation p-value on the excess-R score is below 0.05, AND
3. its Deflated Sharpe (cumulative trial count) is at least 0.90.

Otherwise the result is "not shown", reported as such.

## Expected power (stated in advance)

Entries are about 40% of days, so roughly 1,700 rows, with labels up to 20 days long. I expect on the order of a few hundred effectively independent entries, which can only detect an excess edge of roughly 0.15 R per trade or more. A null result will therefore mean "no detectable edge of that size", not "no edge".
