# Control center: a trader's desk

Design for the front end, drawn on a canvas: https://claude.ai/artifact/BJY7AJLkgNtjdppvZqwF7w (private to the owner). Six screens, all using real numbers read from the project on 15 November 2026. The controls are a prototype and are not connected.

The first version of the canvas was a project status report (gate checklist, job schedules, research phases). A trader needs different things, so it was rebuilt around decisions: what do I hold, what do my signals say, what is waiting for me, what is coming, what can I add or test, and what can go wrong.

## Screens and what each one is for

| Screen | The question it answers | Backed today by | Still to build |
|---|---|---|---|
| Desk | What do I do now? Account, watchlist with signals, approval queue, what moved, calendar, system health | `getrich positions`, `propose`, the briefing and ledger | A UI that reads them; a daily forecast job |
| Pair | What does this instrument look like, and what does the rule and the gate say? | bars, trend and HAR volatility, forecast caches, `propose` | Overlays and the gate preview as an API |
| Backtest | Does this rule work, and how much should I risk? | `getrich replay` (fixed rule), the sizing study | Parameterised runs, trial counter, "promote to paper" |
| Universe | What can I add, and what does a new pair need? | `collect-binance --symbols`, `forecast-run` | Exchange-rule fetch, news tags per coin, one-click add |
| Models | Which forecasts may influence a trade? | `forecast-run`, `forecast-eval` | Scoring on demand, volatility track |
| Orders and risk | What is waiting, what is open, how much can I lose, what alerts me? | `propose`, `approve`, `kill`, `unhalt`, watchdog alerts | Profile switching, user alert rules |

## Things the trader view surfaced

- The trend rule's entry condition is on while BTC is 26% below its 90-day high; the gate would take 0.00059 BTC ($38, $2.46 at risk). Replay says the rule has a Sharpe of 0.38 against 0.86 for buy and hold.
- In the replay, yesterday's 6% fall pushed the rule's drawdown to 15.4%, past the 15% halt.
- BTC and ETH correlate at 0.91 over a year, so the exposure cap counts two positions that are close to one bet.
- Sizing study (16 replays): Sharpe stays between 0.38 and 0.56 whatever the size. Bigger risk buys deeper drawdowns or an earlier halt, not a better rule.
- Gold had 33 events in 24 hours and is not on the watchlist; adding it needs a cTrader or MT5 connection.
- Events are tagged BTC, ETH or crypto market only, so coin-specific news needs the tag list extended before a new pair is useful.
