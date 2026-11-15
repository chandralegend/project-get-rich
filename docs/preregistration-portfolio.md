# Pre-registration: do simple trend and momentum rules across a wider coin universe beat holding?

Written 2026-11-15 BEFORE running the study. Its SHA-256 is logged as an `eval.preregistered` event (`getrich preregister docs/preregistration-portfolio.md`) and `getrich portfolio-study` refuses to run if the hash is not logged. Nothing below may be changed after seeing results; a change is a new study with new trials.

## Why this study

Everything tested so far has been BTC and ETH, which move together (correlation 0.91), so two assets give almost one independent bet. Forecasters and news add no detectable edge. The one lever that has not been tried is more independent bets, using the same plain rules with no fitted parameters. Nothing is tuned: every parameter below is a standard textbook value fixed now.

## Universe (fixed by a rule, not by performance)

BTC, ETH and 14 coins I recall being in the top 20 by market cap in January 2021 and trading against USDT on Binance spot: BNB, XRP, LTC, DOT, ADA, BCH, LINK, XLM, DOGE, UNI, EOS, TRX, XTZ, VET. The list was written from memory before any of these were fetched or looked at; membership was not checked against market-cap data. Daily closes from Binance spot. **Survivorship bias is present and not removable with free data**: coins that vanished before today are not here, which flatters long-only results. EOS lost its Binance USDT market partway (1,973 daily bars against about 2,500), and its position is closed at its last close. A coin enters the eligible set only once it has 256 daily bars.

## Strategies (all long-only spot, no leverage, daily close decisions, held over the next day)

- S0 equal-weight hold: 1/N in every eligible coin. Rebalanced daily without cost, which flatters it slightly, so it is a conservative benchmark.
- S1 trend, equal weight: per coin the existing graded trend signal (three EMA pairs 16/64, 32/128, 64/256; the signal is the fraction of votes up), weight = signal / N_eligible, remainder in cash.
- S2 trend, risk parity: weight per coin proportional to signal / EWMA volatility (lambda 0.94), normalised so the weights sum to the mean signal across eligible coins, never above 1.
- S3 trend, volatility target: S1's portfolio scaled so its trailing 60-day realised volatility is 25% a year, never above 1 times exposure.
- S4 cross-sectional momentum: among eligible coins with signal of at least 2/3, hold the 5 with the highest 90-day return at 20% each; empty slots are cash.
- References (not strategies under test): BTC buy and hold, and the BTC plus ETH equal-weight trend from Phase 1.

## Costs and sizing

10 + 5 bps per side, also run at 2x. A 5% no-trade band per coin, as in the earlier backtests. Reported two ways: at full exposure, and scaled to the approved limits (the "minimal" profile caps total exposure at 20% of equity), because the cap, not the strategy, sets how many dollars a $500 account can make.

## Evaluation

Window 2021-01-30 to the last stored day, the same as earlier phases. Annualised Sharpe, CAGR, maximum drawdown, Sharpe at 2x costs, Sharpe in each half of the window, calendar-year returns, and a 1,000-draw moving-block bootstrap (block 20 days) of the Sharpe difference against each benchmark.

## Trial accounting

S0 to S4 are 5 new trials in the cumulative registry (17 before). Deflated Sharpe uses the full registry.

## Success criteria (all must hold, for each of S1 to S4)

1. Sharpe at 2x costs at least 0.10 above BOTH S0 and BTC buy and hold, AND
2. Deflated Sharpe at least 0.90, AND
3. Sharpe at 2x costs positive in both halves of the window, AND
4. maximum drawdown no worse than 40% at full exposure.

Otherwise "not shown". Four strategies are tested against one benchmark each, so one nominal pass is plausible by chance; the Deflated Sharpe is the only correction applied.

## Expected power and what a pass would mean

About 5.8 years of daily data and 16 coins that share most of their variance with BTC. Differences in Sharpe below about 0.3 are within the noise of one crypto cycle, so only a large gap is detectable. A pass would be a lead to confirm on new data, not proof. Under the minimal profile (20% exposure cap) even a good strategy earns a small number of dollars on $500, which this study reports explicitly.
