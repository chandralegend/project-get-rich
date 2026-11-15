# Pre-registration: an hourly breakout day-trading rule, long and short, with and without leverage

Written 2026-11-15 BEFORE running anything on this rule. Its SHA-256 is logged as an `eval.preregistered` event (`getrich preregister docs/preregistration-futures-breakout.md`) and `getrich replay-futures-study` refuses to run if the hash is not logged. Nothing below may be changed after seeing results; a change is a new study with new trials.

## Why this study

The owner wants the system to behave more like a day trader and to take risk. Everything so far was daily bars, long-only, spot. This study adds shorting and leverage to the real risk gate (`allow_short`, `max_leverage`, margin and liquidation rules in the gate, `docs/futures-design.md`) and asks whether a plain hourly rule earns anything on the hourly BTC and ETH history we hold (2020-01 to now), after realistic costs, funding and a liquidation model.

## The rule (fixed, one parameter set, none tuned)

Decided at each hourly close from data up to and including that bar, per coin (BTCUSDT, ETHUSDT), one position per coin:

- Long when the close is above the highest high of the previous 24 bars AND the 12-bar EMA of the close is above the 48-bar EMA. Short is the mirror (close below the previous 24-bar lowest low and fast EMA below slow EMA).
- Stop at 3 x ATR(24) from the entry close, never tighter than 1.5% (the cost gate refuses stops under about 1.2% at 30 bps round trip). Take profit at 2 x the stop distance. Timeout after 48 bars.
- Every entry goes through `gate.evaluate`; size = the smallest of risk budget (2% of equity), exposure cap, free margin and the liquidation buffer. Exits are simulated at the stop or take-profit level (the open if the bar gapped through it); a bar touching both counts as the stop.
- Costs 10 + 5 bps per side, and 2x. Funding: ASSUMED 0.01% per 8 hours on the notional, longs pay and shorts receive, and 3x that as a stress. Real funding history has not been downloaded. Perp prices are taken equal to spot.
- Maintenance margin 0.5% of gross notional (assumed); liquidation loses the wallet.

## The three variants (the only three ever tried; each is a trial in the cumulative registry, 36 before)

- F0: long only, exposure cap 3x equity, leverage limit 3x.
- F1: long and short, exposure cap 1x, leverage limit 1x (no leverage).
- F2: long and short, exposure cap 3x, leverage limit 3x. **This is the primary** and the one that "shows value" or not.

Limits for all three: a what-if profile that the owner has NOT approved (30% drawdown halt, 5.5% daily loss halt, 2% risk per trade, shorting allowed). Approving leverage or shorting is the owner's decision and would follow only a pass here.

Window: hourly bars from the first F2 entry to the last stored bar. Sharpe is computed from daily returns of the hourly equity curve (annualised with 365 days), as everywhere else.

## Success criteria for F2 (all must hold to "show value")

1. Sharpe at 2x costs at least 1.0 (the gated daily strategy's best is 0.94, so extra trading and risk must beat it clearly), AND
2. Deflated Sharpe at least 0.90, counting every trial in the registry, AND
3. maximum drawdown at most 30% and the drawdown halt never trips, AND
4. Sharpe at 2x costs positive in both halves of the window, AND
5. Sharpe at 2x costs with funding at 3x the assumption still positive, AND
6. at least 150 trades, so the statistic is not carried by a few entries, AND
7. the short side must carry weight: total profit of the short trades at 2x costs above zero, AND
8. zero invariant violations and no liquidation.

Otherwise "not shown". F0 and F1 are reported for context (what shorting adds, what leverage adds) and have no pass bar.

## Expected power and what a pass or a fail would mean

Hourly rules trade a lot, so there will be hundreds of trades, which is enough to measure something. But the cost model (30 bps per round trip, 60 at 2x) against a 1.5%+ stop is a real handicap, and the funding assumption can be wrong in either direction. A fail means this rule family, at these costs, does not clear the bar; it is not proof that no day-trading edge exists. A pass would be a lead to confirm on data not yet seen, not proof, and it would not make leverage safe: leverage scales the loss in a gap, which a stop cannot prevent (the worst 24-hour fall in the data was 46 to 48%).
