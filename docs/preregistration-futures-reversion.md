# Pre-registration: an hourly mean-reversion day-trading rule, long and short, with and without leverage

Written 2026-11-15 BEFORE running anything on this rule. Its SHA-256 is logged as an `eval.preregistered` event (`getrich preregister docs/preregistration-futures-reversion.md`) and `getrich replay-futures-reversion-study` refuses to run if the hash is not logged. Nothing below may be changed after seeing results; a change is a new study with new trials.

## Why this study

The two breakout studies (`docs/phase5-futures-breakout.md`, `docs/phase5-futures-breakout-reset.md`) showed that following hourly breaks loses after costs, and that shorting and leverage amplify the loss. The owner asked to try the opposite family: fade stretched moves and take profit on the way back to the average. Same engine, same gate, same data, costs and funding assumptions, same what-if limits.

## The rule (fixed, one parameter set, none tuned)

Decided at each hourly close from data up to and including that bar, per coin (BTCUSDT, ETHUSDT), one position per coin:

- z = (close - mean of the last 48 closes) / standard deviation of the last 48 closes.
- Long when z is at or below -2.5 (price stretched far below its average); short when z is at or above +2.5.
- Take profit at the 48-bar mean as it stands at entry. The trade is skipped if that target is less than 1.0% away (not enough room to pay costs).
- Stop at 3 x ATR(24) from the entry close, never tighter than 1.5% (the cost gate refuses stops under about 1.2% at 30 bps round trip). Timeout after 24 bars.
- Every entry goes through `gate.evaluate`; size = the smallest of risk budget (2% of equity), exposure cap, free margin and the liquidation buffer. Stops fill at the stop (the open if the bar gapped through it); a bar touching both stop and take profit counts as the stop.
- Costs 10 + 5 bps per side (2x also run). Funding ASSUMED 0.01% per 8 hours on the notional, longs pay and shorts receive (3x as a stress). Maintenance margin 0.5% (assumed).
- The drawdown halt (30%) blocks new entries; 14 days after it trips the owner is assumed to review and reset it (peak restarts), as in the reset study. Reported drawdown is the true one from the all-time peak.

## The three variants (the only three ever tried; each a trial, 42 in the registry before)

- H0: long only (buy stretched dips), exposure cap and leverage limit 3x.
- H1: long and short, 1x (no leverage).
- H2: long and short, up to 3x. **The primary.**

Limits: the same what-if profile (30% drawdown halt, 5.5% daily loss halt, 2% risk per trade, shorting allowed), NOT approved by the owner.

Window: hourly bars from the first H2 entry to the last stored bar. Sharpe from daily returns of the hourly equity curve, annualised with 365 days.

## Success criteria for H2 (all must hold to "show value")

1. Sharpe at 2x costs at least 1.0, AND
2. Deflated Sharpe at least 0.90, counting every trial in the registry (45 with these three), AND
3. true maximum drawdown at most 40%, AND
4. Sharpe at 2x costs positive in both halves of the window, AND
5. Sharpe at 2x costs with funding at 3x the assumption still positive, AND
6. at least 150 trades, AND
7. short trades profitable in total at 2x costs, AND
8. zero invariant violations and no liquidation.

Otherwise "not shown". H0 and H1 are context.

## What a result would mean

Mean reversion on hourly crypto needs a gross edge bigger than about 60 bps per round trip at 2x costs, and fading a stretched move in a trending asset is exactly where a rule gets run over, which is what the 3 ATR stop is for. The most likely outcome is "not shown". A pass would be a lead to test on unseen data and would say nothing yet about whether leverage is wise: the worst 24-hour fall in the data was 46 to 48%, which a stop cannot prevent and leverage multiplies.
