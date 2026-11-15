# Pre-registration: entering the gated volatility-scaled strategy only at 2 of 3 trend votes

Written 2026-11-15 BEFORE running the variant. Its SHA-256 is logged as an `eval.preregistered` event (`getrich preregister docs/preregistration-voltarget-entry.md`) and `getrich replay-voltarget-study` refuses to run if the hash is not logged. Nothing below may be changed after seeing results; a change is a new study with new trials.

## Question

In the gate-compatible volatility-scaled strategy (`docs/phase4-voltarget.md`), the gate forbids adding to a position, so a position opened at one trend vote keeps its small size even if the trend strengthens. Does entering only when at least 2 of the 3 trend pairs are up (instead of 1 of 3) improve the result?

## The two versions compared (everything else identical)

- V1, already run, now counted as a trial: enter when trend signal > 0 (1 of 3 votes or more).
- V2, the variant: enter only when the trend signal is at least 2/3. Sizing, exits, trims, the 3 sigma protective stop, the 10-point trim band, costs, the 0.5 sleeve per coin and the target volatility of 20% are all unchanged. Holding and exit rules are unchanged: a held position stays until the target weight reaches zero, a stop is hit, or it is trimmed.

Same data, window and limits as the first run: BTCUSDT and ETHUSDT daily bars, 2020-05-07 to the last stored day, start equity $500, the approved limits at the time of the run (moderate, 50% exposure, 30% drawdown halt, 5.5% daily halt, 2% risk per trade), costs 10 + 5 bps per side and also 2x.

## Trial accounting

V1 and V2 are 2 new trials in the cumulative registry (34 before). The first run of V1 was looked at before this registration, so it is counted, not treated as free. Deflated Sharpe uses the full registry.

## Success criteria (all must hold for V2 to "show value")

1. Sharpe at 2x costs at least 0.10 above V1 at 2x costs AND at least 0.10 above the gated 2 sigma / 4 sigma trend rule at 2x costs, AND
2. Deflated Sharpe at least 0.90, AND
3. maximum drawdown at most 20%, AND
4. Sharpe at 2x costs positive in both halves of the window, AND
5. zero invariant violations and the drawdown halt never trips.

Otherwise "not shown".

## Expected power and what a pass would mean

One in-sample path on one crypto cycle with about 30 entries. A Sharpe difference below roughly 0.3 is within noise, and the Deflated Sharpe against 36 trials will be hard to clear for any strategy with a Sharpe near 0.8, so a "not shown" is the most likely outcome and would mean only that the data cannot separate the two entry rules. A pass would be a lead to confirm on new data, not proof, and it would not change the fact that buy and hold earned far more over the same window.
