# The trader agent

Added 2026-11-15 at the owner's direction: the system should think like a successful day trader, not rely on forecasting; forecasts and models are inputs to look at.

## What it is

`getrich trader` builds a **desk packet** (everything a trader would look at, computed locally and deterministically) and gives it to Claude (Sonnet 5.5), which returns a typed **trade plan**. The plan is data. It is validated, recorded in the hash-chained insight ledger with the exact packet it saw, run through the deterministic risk gate as a what-if, and scored later against what prices did. With `--propose` the tradable ideas become gate-checked proposals that you approve or reject, exactly like any other order. The agent has no tools, no network, no keys and no way to approve anything.

## What it looks at (agents/desk.py)

| Input | Content |
|---|---|
| Market structure | Daily and hourly views for BTC and ETH: returns, realised volatility, ATR, range position, key levels (prior day, 24 h, 7 d, 30 d), volume vs average, EMA state, breakout and stretch facts; BTC/ETH correlation and relative strength. Closed bars only. |
| Signals and patterns | Facts about the current state (not recommendations), each family labelled with what our own pre-registered tests found (`SIGNAL_RECORD`): daily trend weak, forecasters noise, PI-Net no edge, news timing none, hourly breakout and reversion negative, shorts negative. |
| Forecasts | Newest cached Chronos-2, Kronos and TimesFM probabilities of an up move (flagged if stale), as one weak input among many. |
| News | Classified events from the last 24 h (suspicious items withheld), risk flags, the latest briefing, investigator findings, GDELT attention z-scores. It is told that no economic calendar is connected. |
| Portfolio and risk | Equity, cash, exposure, drawdown, today's P&L, open positions with stops and dollars at risk, pending proposals, halts, the pinned limits, costs and the cost-gate minimum stop (about 1.2%). |
| Its own record | Its last decisions with outcomes and the running scorecard by setup and conviction. |

## What it can say

At most one idea per asset: `open_long`, `hold`, `reduce`, `exit`, `wait` (and `open_short` as a hypothetical that is recorded and scored but cannot be traded; shorting is off in the approved limits and the paper path refuses it). Every open idea has a setup type, a conviction (0 to 1), a thesis, an invalidation, a stop distance, a target, a maximum holding time and a requested risk fraction. The gate can only shrink the size or refuse; a requested risk above the limit is cut to the limit. `wait` is a first-class answer and the prompt tells it to use it often.

## Safety

Everything from the internet reaches it only as structured fields written by another model, with injection-flagged items withheld. It can only cite evidence refs it was shown. Output is schema-constrained and re-validated locally; inconsistent ideas (open when already holding, exit with no position) are dropped and counted. The monthly API cap ($30) is enforced before every call. A plan costs about $0.04 (worst case about $0.10), so four runs a day would be about $5 to $10 a month.

## How it is judged (agents/trader_scoring.py)

No historical backtest: the model has read the history, so a backtest would measure memory. Ideas are scored forward and in shadow. Every `open_long` / `open_short` idea is resolved against the hourly bars after it was issued, with the same rules as the replay engine (entry at the close of the issue bar plus slippage and fee, stop, target, timeout, stop wins a tie, gaps fill at the worse open), giving a net return and R. `getrich trader-card` shows counts, win rate, average R, and results by setup and by conviction. Waiting is not scored, so selectivity is judged only through what it did take. Nothing about it earns trust until a pre-registered number of resolved ideas shows positive net R, which we should set before the first scored sample is large (suggested: 100 resolved ideas, average net R above 0.15, and no single setup carrying it).

## Not yet

Amending a stop on an open position (advice only for now), shorts and leverage in the paper path, an economic calendar, scheduling (manual runs only), and acting on intraday news in real time. Cadence is the owner's call.
