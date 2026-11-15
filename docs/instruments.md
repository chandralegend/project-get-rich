# Instruments

The tradable universe lives in `src/getrich/trading/instruments.py`. Each instrument carries its exchange rules, assumed costs, where its bars come from and when its market is open. The risk gate uses the instrument's own rules and costs; nothing is shared with crypto by accident.

| Class | Symbols | Bars from |
|---|---|---|
| Crypto | BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, LINKUSDT, AVAXUSDT, LTCUSDT | Binance public klines (`collect-binance --symbols ... --timeframe 1d 1h`) |
| Forex (quoted in USD) | EURUSD, GBPUSD, AUDUSD, NZDUSD | Yahoo Finance chart endpoint (`collect-fx`) |
| Forex (inverse series) | JPYUSD = 1/USDJPY, CADUSD = 1/USDCAD, CHFUSD = 1/USDCHF | the same, inverted at collection (high and low swap) |
| Metals | XAUUSD (gold), XAGUSD (silver) | CME futures GC=F and SI=F as proxies for spot |

## What is assumed (and should be replaced by facts before real money)

- **Costs per side:** crypto 10 bps fee + 5 bps slippage (alts 8); forex 0 fee and 1.0 to 2.2 bps slippage standing for half-spread (EURUSD 1.0, GBPUSD 1.5, AUDUSD 1.8, NZDUSD 2.2, JPYUSD 1.8, CADUSD 2.0, CHFUSD 2.2); gold 2.5, silver 6. Overnight financing, swaps and rollover are not modelled, which flatters anything held across days.
- **Order sizes:** crypto filters are paper assumptions (the testnet adapter reads real ones). Forex is assumed to trade in single units and gold and silver in hundredths of an ounce. Many cTrader brokers set 0.01 lot = 1,000 units as the minimum; at $500 without leverage that does not fit, so real forex trading at this size would need leverage, which is not approved.
- **Minimum stop:** crypto 0.5% by default and at least round-trip cost / 0.25R (about 1.2% for BTC); forex majors 0.15%; gold 0.3%; silver 0.4%; always at least the cost-gate minimum.
- **Hours:** forex and metals closed Friday 22:00 UTC to Sunday 22:00 UTC (metals' daily one-hour break is ignored).
- **Data quality:** Yahoo is an unofficial free feed: hourly bars for about two years, daily for a decade, no volume for forex, occasional flat or stale bars. Gold and silver are futures prices with contract rolls. Collection is by hand (`collect-fx` is paced and retries throttling) and is not scheduled or watched by the watchdog.

## Practical sizing at the current limits

With no leverage approved and a 50% exposure cap, a forex position is capped near $250 of notional. On low-volatility instruments the exposure cap, not the 2% risk budget, decides the size, so the dollars at stake are small (a 0.3% stop on $250 risks under $1). That is a property of the limits, not of the instruments.
