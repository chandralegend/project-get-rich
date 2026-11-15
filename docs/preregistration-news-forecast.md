# Pre-registration: does a pretrained forecaster and/or a news stream help the PI-Net?

Written 2026-11-15 BEFORE running the experiment. Its SHA-256 is logged as an `eval.preregistered` event (`getrich preregister`) before the run, and `getrich pinet-experiment` refuses to run if the file's hash is not in the log, so the file cannot be changed afterwards without the mismatch being visible. Nothing below may be changed after seeing results. Any change is a new experiment with new trials.

## Question

On the meta-labelling task already pre-registered (take or skip each trend-rule entry), does giving the PI-Net (a) Chronos-2's forecast features, (b) daily GDELT news features, or (c) both, improve after-cost results over the same model without them, and over taking every entry?

## Primary rule (not a model), samples, labels, strategy, evaluation

Identical to `docs/preregistration-meta-label.md`: trend votes >= 2/3 on BTCUSDT and ETHUSDT daily bars; triple-barrier 4 sigma / 2 sigma / 20 days; costs 10 + 5 bps per side, also judged at 2x; take an entry when the model's expected net R is above zero; equal-weight BTC and ETH sleeves with a 10% no-trade band; 6-group combinatorial purged CV, 2 test groups, 5 out-of-sample paths, embargo 11 days; shift-null permutation test on the excess-R score with 100 draws (linear), 40 (LightGBM), 20 (fusion network).

The only change to the sample: rows are restricted to days that have Chronos-2 features (cached walk-forward forecasts exist from about 2021-05-26) AND every news feature. ALL four variants below use exactly these rows, so differences cannot come from different samples. The cost is a shorter sample than the earlier meta-label run; that is accepted in advance.

## Channels (inputs)

Baseline channels, unchanged: market (19 features), forecast (3 HAR volatility features), context (3 features).

Foundation channel: Chronos-2's cached zero-shot forecasts for horizons 1, 5 and 20 days, as normalised by the daily volatility at the origin: median return, probability of an up move minus 0.5, 80% interval width, and interval skew (width and skew only for horizons above 1). The forecasts are walk-forward and causal by construction (checked in `docs/forecast-eval.md`). Chronos-2 was selected from the earlier forecaster evaluation, in which none of the three forecasters beat a zero-drift random walk on its own; it is used here as an input, not as a signal. That selection used no PI-Net results.

News channel: 16 features from GDELT's DOC API daily timelines (`getrich news-fetch`), fixed in advance in `src/getrich/news/gdelt_timeline.py`: for each of 8 queries (bitcoin; ethereum; cryptocurrency/crypto/stablecoin; hack/exploit/stolen/bankruptcy/collapse with crypto names; regulation/ban/lawsuit/crackdown/SEC with crypto; bitcoin ETF flows; Federal Reserve/FOMC/rate hike/rate cut; inflation/CPI), the trailing 90-day z-score of English-language coverage volume and of average tone. Day t's value is known at the close of day t's bar, when the decision is taken. Missing days are filled forward from the past for at most 7 days; longer gaps remove the row. No lookahead and no other series or queries may be added after seeing results.

## Variants (the full grid, 4 x 3 = 12 trials)

For each of the linear, LightGBM and fusion models, with the same fixed hyperparameters as before and no tuning:

- A: baseline channels
- B: A plus foundation
- C: A plus news
- D: A plus foundation plus news

The fusion network treats each channel as its own encoder with a learned gate, as in Phase 2; the linear and LightGBM models see the concatenated columns.

## Comparators

1. The same model on variant A (does the added channel help?).
2. The primary rule alone, taking every entry (does the model add anything at all?).
3. The graded trend baseline and buy and hold, reported for context.

## Trial accounting

Every variant and the primary-rule comparator count as trials in the cumulative registry (`docs/trials.json`). The registry holds 17 trials before this experiment; this adds 12 variants, so the Deflated Sharpe is computed against 29 plus the comparator. Variants A are included even though they are references, because their results were also looked at.

## Success criteria (all must hold, separately for each of B, C and D and each model)

A variant "shows value" only if:
1. its mean path Sharpe at 2x costs exceeds BOTH the same model on A and the primary rule alone, each by at least 0.10, AND
2. its shift-null permutation p-value on the excess-R score is below 0.05, AND
3. its Deflated Sharpe (cumulative trial count) is at least 0.90.

Otherwise it is reported as "not shown". If some variants clear the bar, they are reported alongside the number tried (9 non-reference variants), and the Deflated Sharpe is the only multiple-testing correction applied. A single marginal pass among nine should be read with that in mind and treated as a lead to confirm on out-of-sample time, not a result.

## Expected power (stated in advance)

Restricting to days with Chronos-2 features shortens the sample from 2,302 to 2,078 entry rows (BTC 1,071, ETH 1,007; 2021-05-26 to 2026-10-25), measured on the forecaster cache before any news or PI-Net result was looked at; adding the news restriction can only remove a few more. Labels run up to 20 days, so there are perhaps 150 to 250 effectively independent entries. That can only detect an excess of roughly 0.15 to 0.2 R per trade or more. A null result therefore means "no detectable edge of that size on this sample", not "no edge". With 3 models and 3 added variants, about one nominal pass at p < 0.05 is expected by chance even if nothing works, which is why all three criteria are required together.

## What is exploratory and not part of this registration

The `getrich news-study` event study (news features against forward returns) and every `getrich pinet-train` run are exploratory, are not registered, and are not evidence for or against the criteria above. They exist to look at the data and to let the user select a forecaster and train; any result worth acting on must be confirmed by a new pre-registered experiment.
