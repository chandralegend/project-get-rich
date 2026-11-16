# Pre-registration: the live PI-Net, scored forward on decisions it makes in real time

Written 2026-11-16 BEFORE the first live prediction is recorded. Its SHA-256 is logged as an `eval.preregistered` event (`getrich preregister docs/preregistration-pinet-forward.md`), and `getrich pinet-live` refuses to record anything until that hash is logged. Nothing below may be changed after seeing results; a change is a new study with new trials.

## Why this study

The pre-registered ablation (`docs/news-forecast-results.md`) found that no PI-Net variant earns its place: the best, `lgbm` with the Chronos-2 channel, reached a Sharpe of 0.45 at 2x costs against 0.58 for taking every trend entry, and failed the shift-null and Deflated Sharpe criteria. That test used history, where Chronos-2's forecasts for 2021 to 2025 may have been informed by data it was pretrained on. This study asks the one question history cannot answer cleanly: does the frozen model rank trades correctly on decisions made after it was trained, with nothing known in advance?

It changes no trading behaviour. The PI-Net stays a displayed shadow input; the trader is told it has no demonstrated edge until this study says otherwise.

## What is frozen

- The model: `pinet-lgbm-chronos2-nonews.pkl` (LightGBM, market + forecast + context + Chronos-2 channels, 35 features, trained on 2078 rows from 2021-05-26 to 2026-10-25), SHA-256 `3fcca104e7a75724bea3c9ee91e54adcee7c8ec361a9d845c28ab3b7a030762a`. The code refuses to run on any other file. No refit, ever, inside this study; a refit is a new study.
- The features: the same `features.feature_frame` and `features.foundation_frame` code that built the training rows (one function, tested to give the same numbers for a past day whether or not later bars exist).
- The decision rule from the research: a decision is taken at the close of a daily bar, for BTCUSDT and ETHUSDT, only when the trend rule's vote is at least 2 of 3 (the model's domain). The model outputs p (probability the trade ends with positive net R) and e (expected net R). The call is **take** when e > 0, otherwise **skip**.
- The trade each decision describes: enter at that bar's close; take profit at +4 sigma, stop at -2 sigma (sigma = the 20-day EWMA daily volatility at that bar), timeout at the close 20 daily bars later; a bar touching both barriers counts as the stop; costs 10 bps fee and 5 bps slippage per side (the project's `CostModel`); outcome in R = return / stop distance minus cost in R. These are the research's `META_KWARGS` and labelling code; the live resolver is tested to match it.
- Every decision (take and skip, in the model's domain) is stored in the hash-chained ledger on the day it is made, with its exact inputs, and resolved later against the daily bars that followed. Nothing is backfilled: decisions before this document's hash was logged do not exist in the study.

## The checkpoint (one verdict, set now)

The verdict is computed once, at the later of: 180 days after the first recorded decision, and 150 resolved decisions in the model's domain. Before that, screens show counts and running means labelled "interim, not a verdict", and nobody changes anything because of them.

## Success criteria (all must hold to "show value")

Let `take` be the resolved decisions the model said to take, and `all` every resolved decision in the model's domain (what taking every trend entry would have earned).

1. mean net R of `take` minus mean net R of `all` is at least +0.10 R, AND
2. a moving-block bootstrap of that difference gives a one-sided p below 0.05 (blocks of 20 calendar days with both coins' decisions of those days resampled together, 10,000 draws, seed 20261116; p is the share of draws with a difference of zero or less), AND
3. mean net R of `take` at 2x costs is positive, AND
4. at least 40 `take` decisions are resolved, AND
5. the model file's hash is unchanged.

Otherwise: "not shown". There is no second chance by changing the model or the rule.

## What a result would mean, stated plainly

- The statistical power is low. BTC and ETH move together (correlation about 0.9) and decisions overlap for up to 20 days, so 180 days is about nine independent blocks. The study can only detect a large effect; a failure is NOT proof of no edge, it is "not shown", and the model stays unused.
- A pass would be a lead, not permission: the next step would be a small, owner-approved role for the PI-Net as a filter on trades the trader already wants, still paper, still gated.
- The study is counted as one trial. At the verdict it is added to `docs/trials.json` with the annualised Sharpe of the daily mean net R of the `take` decisions (a crude number, declared in advance), so later Deflated Sharpes count it.
