# Pre-registration: the hourly breakout rule when the owner resets the drawdown halt after a cool-off

Written 2026-11-15 BEFORE running it. Its SHA-256 is logged as an `eval.preregistered` event (`getrich preregister docs/preregistration-futures-reset.md`) and `getrich replay-futures-reset-study` refuses to run if the hash is not logged. Nothing below may be changed after seeing results; a change is a new study with new trials.

## Why this study

The first study (`docs/preregistration-futures-breakout.md`, results `docs/phase5-futures-breakout.md`) said "not shown", but its drawdown halt latched for good: the 30% halt tripped on 2020-07-14 for F2, 2021-11-15 for F1 and 2022-01-09 for F0, and the replay never reset it, so most of the window was never traded. In real use the owner reviews and runs `unhalt`. This study models that and nothing else: same rule, same data, same costs, same limits.

## What changes (one rule, one value, none tuned)

- The rule, costs, funding assumption (0.01% per 8 hours, longs pay), maintenance margin, variants and window are exactly those of the first study.
- When the 30% drawdown halt trips, no new entries are allowed (open positions keep their stops and exits), exactly as before. After 14 days (336 hourly bars) the owner is assumed to review and reset: the halt clears and the peak used for the drawdown test restarts at the then-current equity. 14 days is the only cool-off ever tried. The reset can happen repeatedly.
- Reported drawdown is the true one, from the all-time peak of the equity curve, not from the reset peak.

## The three variants (the only three ever tried; each a trial, 39 in the registry before)

- G0: long only, exposure cap and leverage limit 3x.
- G1: long and short, 1x (no leverage).
- G2: long and short, up to 3x. **The primary.**

## Success criteria for G2 (all must hold to "show value")

1. Sharpe at 2x costs at least 1.0, AND
2. Deflated Sharpe at least 0.90, counting every trial in the registry (42 with these three), AND
3. true maximum drawdown at most 40% (a reset restarts the halt's reference, so this bounds the real worst case across resets), AND
4. Sharpe at 2x costs positive in both halves of the window, AND
5. Sharpe at 2x costs with funding at 3x the assumption still positive, AND
6. at least 150 trades, AND
7. short trades profitable in total at 2x costs, AND
8. zero invariant violations and no liquidation.

Otherwise "not shown". G0 and G1 are context. The number of halts and the dates are reported.

## What a result would mean

The first study's numbers say the rule had no edge before its halt in most variants (F2 made money only in 2020, shorts lost throughout), so the most likely outcome is "not shown" again, now over the full window. A pass would be a lead to confirm on unseen data, not a reason to approve leverage by itself, and the gap risk stays: the worst 24-hour fall in the data was 46 to 48%, which a stop cannot prevent and leverage multiplies.
