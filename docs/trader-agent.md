# The trader agent

Added 2026-11-15 at the owner's direction: the system should think like a successful day trader, not rely on forecasting; forecasts and models are inputs to look at.

## What it is

`getrich trader` builds a **desk packet** (everything a trader would look at, computed locally and deterministically) and gives it to Claude (Sonnet 5.5), which returns a typed **trade plan**. The plan is data. It is validated, recorded in the hash-chained insight ledger with the exact packet it saw, run through the deterministic risk gate as a what-if, and scored later against what prices did. With `--propose` the tradable ideas become gate-checked proposals that you approve or reject, exactly like any other order. The agent has no tools, no network, no keys and no way to approve anything.

## What it looks at (agents/desk.py)

| Input | Content |
|---|---|
| The whole universe | One compact row per instrument (class, open now, data age, price, 24 h / 7 d / 20 d returns, the 24 h move in units of its own volatility, volatility, trend votes, drawdown, 7 d range position, stretch from the 48 h mean, round-trip cost, minimum stop) for 10 crypto pairs, 7 forex pairs, gold and silver. The agent compares them and picks; most get no idea. |
| Market structure | Full detail for BTC and ETH, anything held, and the four non-core instruments that moved most for their own volatility. Daily and hourly views: returns, realised volatility, ATR, range position, key levels (prior day, 24 h, 7 d, 30 d), volume vs average, EMA state, breakout and stretch facts; BTC/ETH correlation and relative strength. Closed bars only. |
| Signals and patterns | Facts about the current state (not recommendations), each family labelled with what our own pre-registered tests found (`SIGNAL_RECORD`): daily trend weak, forecasters noise, PI-Net no edge, news timing none, hourly breakout and reversion negative, shorts negative. |
| Forecasts | Newest cached Chronos-2, Kronos and TimesFM probabilities of an up move (flagged if stale), as one weak input among many. |
| News | Classified events from the last 24 h (suspicious items withheld), risk flags, the latest briefing, investigator findings, GDELT attention z-scores. It is told that no economic calendar is connected. |
| Portfolio and risk | Equity, cash, exposure, drawdown, today's P&L, open positions with stops and dollars at risk, pending proposals, halts, the pinned limits, costs and the cost-gate minimum stop (about 1.2%). |
| Its own record | Its last decisions with outcomes and the running scorecard by setup and conviction. |

## What it can say

At most one idea per instrument (six in all), chosen from the whole universe, with `universe_view` saying what it looked at and why it passed on the rest: `open_long`, `hold`, `reduce`, `exit`, `wait` (and `open_short` as a hypothetical that is recorded and scored but cannot be traded; shorting is off in the approved limits and the paper path refuses it). Every open idea has a setup type, a conviction (0 to 1), a thesis, an invalidation, a stop distance, a target, a maximum holding time and a requested risk fraction. The gate can only shrink the size or refuse; a requested risk above the limit is cut to the limit. `wait` is a first-class answer and the prompt tells it to use it often.

## Safety

Everything from the internet reaches it only as structured fields written by another model, with injection-flagged items withheld. It can only cite evidence refs it was shown. Output is schema-constrained and re-validated locally; inconsistent ideas (open when already holding, exit with no position) are dropped and counted. The monthly API cap ($30) is enforced before every call. A plan costs about $0.04 (worst case about $0.10), so four runs a day would be about $5 to $10 a month.

## How it is judged (agents/trader_scoring.py)

No historical backtest: the model has read the history, so a backtest would measure memory. Ideas are scored forward and in shadow. Every `open_long` / `open_short` idea is resolved against the hourly bars after it was issued, with the same rules as the replay engine (entry at the close of the issue bar plus slippage and fee, stop, target, timeout, stop wins a tie, gaps fill at the worse open), giving a net return and R. `getrich trader-card` shows counts, win rate, average R, and results by setup and by conviction. Waiting is not scored, so selectivity is judged only through what it did take. Nothing about it earns trust until a pre-registered number of resolved ideas shows positive net R, which we should set before the first scored sample is large (suggested: 100 resolved ideas, average net R above 0.15, and no single setup carrying it).

## Instruments (trading/instruments.py, docs/instruments.md)

Crypto (Binance spot): BTC, ETH, SOL, BNB, XRP, ADA, DOGE, LINK, AVAX, LTC. Forex (Yahoo Finance): EURUSD, GBPUSD, AUDUSD, NZDUSD, plus JPYUSD, CADUSD and CHFUSD, which are 1 / USDJPY, 1 / USDCAD and 1 / USDCHF so every series is quoted in dollars (long JPYUSD = short USDJPY). Metals: gold and silver as CME futures proxies (GC=F, SI=F). Each instrument has its own exchange rules, assumed costs (forex spreads far below crypto fees), minimum stop, bar source and trading hours (forex and metals are closed from Friday 22:00 to Sunday 22:00 UTC; the gate refuses entries then, and ideas on a closed market are dropped before scoring).

## Not yet

Real execution on forex (no broker connected; everything is paper), swaps and rollover costs, intraday news in real time, and a refresh step inside `getrich trader` (run `collect-fx` and `collect-binance` first so data is fresh). Amending a stop on an open position (advice only for now), shorts and leverage in the paper path, an economic calendar, scheduling (manual runs only), and acting on intraday news in real time. Cadence is the owner's call.


## Fresh inputs (2026-11-16)

A plan made on stale headlines is worse than none, so a real trader run (CLI or UI) first calls `ops/prepare.py`, one step after another, each allowed to fail alone:

1. market data for the classes in scope (Binance for crypto, Yahoo for forex and metals),
2. the central-bank feeds and the open-web news,
3. classification of the newest 60 unclassified stories (Haiku, newest first),
4. a new briefing if the last one is older than 8 hours (one Sonnet call, a few cents).

What happened, and how old each input is afterwards, goes into the packet's `freshness` section, and the system prompt tells the trader to discount stale or incomplete news and to say so in `edge_check`. `--no-refresh` (CLI) or the tick-box on the Trader screen skips it. A dry run never refreshes unless `--refresh` is given.

Why this was added: the hourly classification job stopped at a daily cap of 200 items by midday UTC and worked oldest first, so fresh headlines queued behind a backlog and the packet's "news" was up to a day old. The cap is now 500 (about $0.35 a day at Haiku prices; the monthly budget cap is the real limit) and the queue is newest first.

Also fixed in the same change: times inside the packet (briefing, flags, findings, journal) were the container's local time (Asia/Colombo) under a UTC heading; they are UTC now, and every event carries `published_hours_ago`.

Not refreshed by a run, on purpose: the forecasters (Kronos, Chronos-2, TimesFM) and the PI-Net. They need torch and model weights, which the Docker image leaves out. The forecast caches are walk-forward results for BTC and ETH made on the host, and each forecast in the packet shows its origin date. There is no live PI-Net output; the models were research, found no edge, and the packet says so.


## PI-Net as an input (2026-11-16)

The packet carries a frozen PI-Net's call for BTC and ETH (`markets.<coin>.pinet`: take, skip, or out of domain when the trend rule is not long) and the study's running numbers (`freshness.pinet`). The system prompt tells the trader it has no demonstrated edge and is being scored forward (docs/preregistration-pinet-forward.md), so it is weighed as noise until the pre-registered checkpoint says otherwise. Nothing about the gate, sizing or approvals changes.
