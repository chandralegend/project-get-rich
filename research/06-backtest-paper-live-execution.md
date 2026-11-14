# Track 6: Backtest -> Paper -> Live Execution (stocks, FX, gold/silver)

Researched 2026-11-14. Local-first constraint applied (only cloud LLMs = Anthropic Claude; execution runs on the user's own machine/server).

**Evidence conventions.** "Seen" = I read it on that date (GitHub API / PyPI JSON / vendor docs). "Unverified" = secondary source, single blog, or my own background knowledge not re-checked. Star counts and push dates are from the GitHub API on 2026-11-14; PyPI versions/dates are from the PyPI JSON API on the same day. Nothing here is legal, tax or investment advice. The user's country is unknown and changes many answers (see Open Questions).

---

## 1. TL;DR

1. **Best fit for "one codebase, backtest -> paper -> live", fully local: NautilusTrader + Interactive Brokers (IB Gateway) as the single broker.** Nautilus' stated design is that the same strategy/execution-algorithm code runs in backtest and live (repo README, https://github.com/nautechsystems/nautilus_trader, 31.5k stars, pushed 2026-11-14, LGPL-3.0). Its IB adapter is marked Stable and its docs reference `XAUUSD.IBCMDTY` (spot gold) and IDEALPRO FX handling (https://nautilustrader.io/docs/latest/integrations/interactive_brokers/). IBKR is the only candidate that covers equities + FX + spot metals (+ futures MGC/SIL) in one API with a real paper account.
2. **Big caveat on Nautilus:** the integrations list has **no OANDA, no Alpaca, no MT5 adapter** (https://nautilustrader.io/docs/latest/integrations/). For FX/metals your only built-in route is IB. Also, it is mid-transition v1 -> v2: PyPI stable is 1.231.0 (2026-08-02) while 2.0.0rc9 landed 2026-11-10; the README warns RC/dev wheels are not recommended for real capital and breaking changes happen between releases.
3. **Runner-up: LEAN CLI run locally** (Apache-2.0, 22.5k stars, pushed 2026-11-13). Supports IB, OANDA (FX + CFD), Tradier, Alpaca, plus its own paper brokerage, in Docker on your machine. Catch: the most recent QuantConnect staff answer I could find says local live deployment needs a paid "Researcher" seat (official price $84/mo, $888/yr), though the thread text was not fully retrievable (unverified).
4. **IBKR automation is getting harder to run unattended:** IBC (the standard IB Gateway auto-login tool) was **retired and archived 1 Sep 2026** (README seen). IBKR 2FA still needs IBKR Mobile approval periodically. Plan for a human-in-the-loop re-auth about weekly, and for the risk that IBC bit-rots.
5. **Paper trading overstates live results.** Alpaca paper fills against NBBO only, with *random* partial fills, no slippage/liquidity/queue modeling; IBKR paper simulates stops and fills at top-of-book and lacks some order types; one practitioner found paper accepted conflicting orders that live rejected. Treat paper as a *plumbing test*, not a P&L estimate. Calibrate costs from micro-live fills.
6. **US PDT rule is gone:** FINRA Regulatory Notice 26-10 replaced day-trading margin rules with an intraday margin framework, effective **2026-06-04**; brokers may phase in until **2027-10-20** so your broker's implementation date matters (https://www.finra.org/rules-guidance/notices/26-10, seen).
7. **Local-first live trading is feasible but uptime is the real engineering problem**, not the framework: a sleeping Mac, a macOS auto-update reboot, or an un-approved IBKR 2FA prompt will silently stop trading. Prefer an always-on small box (Mac mini / mini-PC / low-cost VPS under your control) with broker-side protective orders, and keep LLMs *out of the order path*.

---

## 2. Framework comparison

Stars / last push from GitHub API (seen 2026-11-14). "Live" and "Paper" refer to the framework's own ability; "FX/Metals" = reachable via a first-party/bundled broker integration.

| Framework | URL | Stars | Last push | License | Style | Live | Paper | Equities | FX | Metals | Parity / notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **NautilusTrader** | https://github.com/nautechsystems/nautilus_trader | 31.5k | 2026-11-14 | LGPL-3.0 | Event-driven (Rust core + Python) | Yes | Via IB paper port (4002/7497); no built-in simulated-venue paper mode seen | Yes (IB) | Yes (IB IDEALPRO) | Yes via IB (`XAUUSD.IBCMDTY`, futures) | Strongest parity story; same kernel in backtest/live. PyPI 1.231.0 (2026-08-02); v2 RCs through 2.0.0rc9 (2026-11-10). One `LiveNode` per process. HN launch thread 208 pts (https://news.ycombinator.com/item?id=44810552) |
| **QuantConnect LEAN** (OSS engine + `lean-cli`) | https://github.com/QuantConnect/Lean ; https://github.com/QuantConnect/lean-cli | 22.5k | 2026-11-13 | Apache-2.0 | Event-driven (C#, Python algos) | Yes (local Docker via `lean live deploy`, or cloud nodes) | Yes (own paper brokerage, local) | Yes (IB, Tradier, Alpaca, Schwab, etc.) | Yes (IB, OANDA) | CFD/spot-metals via OANDA/IB CFD; docs list no dedicated metals broker (seen) | Very mature; same algo cloud/local. Local-first caveats: Docker required; Researcher seat likely required for local live (unverified); data downloads need account. Cloud pricing: Free (no live), Researcher $84/mo (2 live nodes), Team $168/mo (10), Trading Firm $480/mo (https://www.quantconnect.com/pricing.md, seen) |
| **vectorbt (OSS)** | https://github.com/polakowo/vectorbt | 9.8k | 2026-11-11 | Apache-2.0 + Commons Clause (SPDX "NOASSERTION") | Vectorized (Numba) | No | No | Data-agnostic | Data-agnostic | Data-agnostic | Fastest research/sweeps; **no live path**: port winners to Nautilus/LEAN. PyPI 1.2.1 (2026-11-11) |
| **vectorbt PRO** | https://vectorbt.pro/ | n/a (private) | "2026.10.5" referenced | Paid, private repo | Vectorized + more engines | Not described; "not a hosted trading bot, connect your own broker via custom data classes" | No | agnostic | agnostic | agnostic | $25/mo, $225/yr, or $500 lifetime via sponsorship (seen). Research tool only |
| **backtrader** | https://github.com/mementum/backtrader | 23.7k | 2024-08-19 | GPL-3.0 | Event-driven | Historically IB/Oanda via stores (unverified current health) | Via broker | Yes | Yes (old stores) | Via IB | **Effectively unmaintained**: last PyPI 1.9.78.123 on 2023-04-19, last push Aug 2024. Large tutorial base; forks exist (not evaluated) |
| **Backtesting.py** | https://github.com/kernc/backtesting.py | 9.2k | 2026-08-05 | AGPL-3.0 | Event-ish, single-asset | No (unverified) | No | agnostic | agnostic | agnostic | Simple/fast single-instrument prototyping; AGPL matters if you ever distribute. PyPI 0.6.6 (2026-07-22) |
| **zipline-reloaded** | https://github.com/stefan-jansen/zipline-reloaded | (rate-limited, not seen) | PyPI 3.2.1 on 2026-10-25 | Apache-2.0 (unverified) | Event-driven, daily-bar equities heritage | No first-party live (unverified) | No | Yes | Weak | Weak | Research-oriented (ML4T book ecosystem); not a live engine |
| **bt** | https://github.com/pmorissette/bt | 3.0k | 2026-11-13 | MIT | Portfolio-level / allocation backtests | No | No | agnostic | agnostic | agnostic | Good for rebalancing/allocation research. PyPI 1.4.1 (2026-10-10) |
| **Lumibot** | https://github.com/Lumiwealth/lumibot | 2.2k | 2026-11-14 | GPL-3.0 | Event-driven | Yes (README: "12 brokers", stocks/options/futures/forex/crypto/prediction markets; full list not shown; Alpaca is the documented example) | Yes (broker paper, e.g. Alpaca) | Yes | Claimed | Not mentioned | "Keep strategy class, swap data source + broker runner". Optional hosted offering BotSpot.trade (avoid for local-first). PyPI 4.6.57 (2026-11-14), very active release cadence |
| **MetaTrader 5 + Python pkg** | https://pypi.org/project/MetaTrader5/ | n/a | PyPI 5.0.6231 (2026-09-27) | MIT per PyPI metadata (terminal is proprietary) | Terminal-centric (EAs) / Python polling | Yes (via broker's MT5 terminal) | Yes (demo accounts) | Broker-dependent | Yes | Yes (most MT5 FX/CFD brokers list XAUUSD) | **Windows-only package**; Mac needs Wine/Parallels/Windows VM; community bridges exist (meta-trader-mcp, siliconmetatrader5) and a mock (MMetaTrader5) (https://www.mql5.com/en/forum/478849, https://pypi.org/project/siliconmetatrader5/). Bad fit for local-first on Apple Silicon unless you accept a Windows VM/VPS |
| **Freqtrade** | https://github.com/freqtrade/freqtrade | 56.9k | 2026-11-12 | GPL-3.0 | Strategy loop (candle-based) | Yes | Yes ("dry-run") | No | No | No | Crypto-only. Lesson: dry-run uses exchange-default (lowest-tier) fees while live uses real fees (community tutorial, secondary). Release 2026.10 (2026-10-30) |
| **Jesse** | https://github.com/jesse-ai/jesse | 8.8k | 2026-11-10 | MIT | Event-driven | Yes (paid live plugin: unverified) | Yes | No | No | No | Crypto-only; architecture reference only |
| **Hummingbot** | https://github.com/hummingbot/hummingbot | 21.2k | 2026-11-13 | Apache-2.0 | Event-driven connectors | Yes | Paper connectors | No | No | No | Crypto market-making; connector architecture reference only |
| **OpenAlgo** | https://github.com/marketcalls/openalgo | 3.0k | 2026-11-13 | AGPL-3.0 | Self-hosted REST bridge + strategy host | Yes | "API Analyzer" sandbox | India (NSE/BSE etc.) | Not mentioned | MCX only via Indian brokers | 38 broker plugins, mostly Indian. **Not relevant** unless you trade Indian markets (seen) |
| **ib_async** (library, not framework) | https://github.com/ib-api-reloaded/ib_async | 1.8k | 2026-11-13 | BSD-2-Clause | Async IB wrapper | Yes | IB paper | Yes | Yes | Yes | Maintained successor to ib_insync; PyPI 2.1.0 (2025-12-08). Foundation for a thin custom engine |
| **PyBroker** | https://github.com/edtechre/pybroker | 3.7k | 2026-11-09 | NOASSERTION | Vectorized-ish ML-friendly walk-forward | Limited (unverified) | No | Yes | No | No | Built-in walk-forward + ML workflow; research tool |
| **hftbacktest** | https://github.com/nkaz001/hftbacktest | 5.1k | 2025-12-23 | MIT | Latency-aware L2/L3 tick sim | Limited | No | n/a | n/a | n/a | Only if you go HFT/market-making; probably out of scope |
| **QSTrader** | https://github.com/mhallsmoore/qstrader | 3.5k | 2024-06-30 | MIT | Event-driven | Alpha | No | Yes | No | No | Stale |
| Newer/niche entrants (found via search; not deeply vetted) | tradedesk (IG live): https://github.com/radiusred/tradedesk ; pyeventbt (MT5 mock for parity): https://pypi.org/project/pyeventbt/ ; ml4t-backtest (beta): https://pypi.org/project/ml4t-backtest/ ; quanttrader: https://github.com/letianzj/quanttrader | - | - | - | Event-driven | Varies | - | - | - | - | I found **no clearly dominant 2025-26 newcomer**; the notable "new" development is NautilusTrader's v2/Rust-native line. Treat the others as hobby-scale until proven |
| Out of scope (other tracks) | TradingAgents https://github.com/TauricResearch/TradingAgents (122k stars); FinRL https://github.com/AI4Finance-Foundation/FinRL (17k) | | | | | | | | | | LLM-agent / RL research stacks, not execution engines |

**Key criterion check (parity):**
- Nautilus: best parity by design, but docs themselves warn live can differ from simulation in "venue, transport, timing, persistence, and reconciliation behavior".
- LEAN: parity good; paper brokerage is local and uses live data with simulated capital.
- vectorbt/bt/Backtesting.py/zipline: **no parity** (research only). Use them for idea screening, then re-implement/port, and require the port to reproduce the vectorized result within tolerance on the same data.
- Lumibot: parity claimed via swapping broker/data runner; check its "execution gap" doc before relying.

---

## 3. Broker / venue comparison

Fee and availability numbers below are only those I actually saw; "not found" means I searched and did not retrieve it.

| Broker / API | Stocks | FX | Metals (XAU/XAG) | Paper trading | API quality / notes | Fees (seen) | Min. account | Jurisdiction caveats |
|---|---|---|---|---|---|---|---|---|
| **Interactive Brokers** (TWS/IB Gateway API, ib_async; Client Portal Web API) | Yes (global) | Yes (IDEALPRO) | Yes: London spot gold/silver (XAUUSD-style `IBCMDTY`), US residents get separate "US Spot Gold" product (not in AZ, MT, NH, RI); also CME futures MGC/SIL (futures coverage: Nautilus doc + general knowledge) | Yes, separate paper account (ports 7497 TWS / 4002 Gateway). Fidelity limits: stops/complex orders simulated; fills against top of book; some order types unsupported (VWAP, Auction, RFQ, Pegged-to-Market) per IBKR campus list as relayed by third parties | Most complete retail API; needs a running Java Gateway/TWS; daily restart design; periodic 2FA via IBKR Mobile; message pacing ~ market-data-lines/2 per sec (default 50/s), 3 breaches terminate session (IBKR docs via search); historical-data pacing limits | Spot metals: 1.5 bp up to $500k/month tier, 2.0/1.0/0.7 bp lower tiers on some regional pages, $2 per-order minimum on tier 1, storage 0.10% p.a. on London gold; US gold: $0.15/oz/month storage (https://gdcdyn.interactivebrokers.com/en/pricing/commissions-metals.php, via search). FX commission schedule: **not retrieved** (page 403) | "No universal minimum" per third-party (unverified) | Broadest global availability of the set; metals product differs by residency. Entity/regulator rules vary |
| **Alpaca** (REST/WebSocket; alpaca-py 0.45.0 on 2026-11-05) | Yes (US equities, options) | **No** (not found in docs/QC list) | **No** | Yes, free paper; fills vs NBBO, random partial fills (10% chance reported), no liquidity/slippage/queue model, some reports of multi-minute fill delays (forum) | Clean modern API; great for equities prototyping | Commission-free equities (marketing; verify) | Not found | US-focused; non-US access limited (unverified) |
| **OANDA v20** | CFDs only | Yes | Yes (XAU_USD, XAG_USD style CFD instruments; availability varies by regional entity) | Yes: free demo ("practice"), different base URL, reported delayed data on practice (third-party, unverified) | REST + streaming; token from account portal. **v20 API not available to OANDA Global Markets and OANDA TMS Brokers S.A.** (OANDA docs, seen). Python lib `oandapyV20` last release 2021 (v20-python repo last push 2021) so use REST directly | Spread-based; I found no current sourced XAU spread | Not found | Entities: US (CFTC/NFA), UK (FCA), Singapore, Japan, Australia, Canada listed; EU not named. US retail cannot trade CFDs; metals on US entity unverified |
| **Tradier** | Yes (US equities/options) | No | No | Sandbox exists (general knowledge; unverified) | Simple REST | Not retrieved | Not retrieved | US only |
| **Saxo (OpenAPI)** | Yes | Yes | Yes (CFD/spot metals; unverified per-instrument) | Yes: SIM env with simulated $100k, "matching live functionality except instrument/market-data limits"; default dev sim account may be FX-only until requested (docs, seen) | Strong docs; live token flow requires application key/secret; one-day tokens are SIM-only; Saxo says direct retail may use OpenAPI for personal use (Saxo help center) but live key route for retail is unclear | Not retrieved | "from $0" per third party, unverified | Regional entity dependent; US not served (unverified) |
| **cTrader Open API** (broker-supplied cTrader accounts; Python lib from Spotware) | Broker-dependent | Yes | Broker-dependent (forum shows a user who saw GOLD in asset list but not symbols) | Yes: demo accounts supported by Open API | Protobuf/TCP API, community Python wrappers; `ctrader-open-api` PyPI last release 2024-06-26 | Per broker | Per broker | Per broker (many ECN/CFD brokers are non-US/EU-regulated offshore: due diligence required) |
| **MT5 brokers** | CFD stocks mostly | Yes | Yes (XAUUSD common) | Demo accounts | Windows-only Python package; EAs in MQL5; Mac impractical | Per broker | Per broker | Per broker; check EA/algo/scalping policies in each broker's terms |
| **Capital.com API** | CFDs | Yes | Yes (GOLD epic seen in unofficial tools) | Yes: demo base URL `demo-api-capital.backend-capital.com` | REST + WebSocket; rate-limit figures conflict among third parties (1945/min vs 10/s) | Spread-based | Not retrieved | CFD broker: not for US residents (general knowledge; unverified here); EU/UK leverage caps apply |
| **IG REST API** | CFDs/spread bets | Yes | Yes | Demo (requires same email as live) | Default limits per IG Labs FAQ: 60 non-trading req/min per app, 10,000 historical data points/week; "no possibility to increase" | Spread-based | Not retrieved | Not US retail (unverified); UK/EU/AU etc. Python lib `trading-ig` |
| **Tradovate** (futures; CME micros MGC/SIL) | Futures only | Currency futures | Yes (CME) | Sim exists, but API needs funded live account (see right) | API requires a funded live account with >= ~$1,000 equity and a ~$25/mo API add-on; CME data agreement extra; third-party estimates $315-$530/mo all-in (all unverified blogs) | See left | ~$1,000 for API (unverified) | US/CME futures brokers; futures are not subject to PDT; tax treatment differs (Section 1256) |
| **FXCM** | CFDs | Yes | Yes | Demo (REST enabled by default in old docs) | **Conflicting signals:** one library changelog says FXCM deprecated its public trading API in 2026 and protocol continues under Forex.com; a June 2026 review still promotes it. Docs I found date from 2017-2019 | Spread-based | Not retrieved | Regional; verify before building anything on it |
| Others named by QC as LEAN-supported (not researched): TradeStation, tastytrade, Schwab, Public, Webull, Clear Street (equities/options/futures) | | | | | | | | |

**Alternatives for metals that avoid CFDs:** (a) IBKR spot metals; (b) CME micro futures MGC (gold) / SIL (silver) via IBKR or a futures broker; (c) physical-metal ETFs (GLD/SLV/IAU) through any stock broker (tax caveat below). Which is right depends heavily on residency (CFDs are restricted/prohibited for retail in some places).

---

## 4. The paper-vs-live gap

### 4.1 Why paper overstates live (with evidence)
| Cause | Evidence / mechanism |
|---|---|
| Fills assume the quote, no impact | Alpaca paper fills against NBBO only, order size not checked against quoted size, no volatility/liquidity modeling (Alpaca forum, https://forum.alpaca.markets/t/does-a-paid-account-give-more-accurate-paper-market-fills/14303 and docs https://docs.alpaca.markets/docs/paper-trading) |
| Synthetic randomness in partials | Alpaca: random partial fills (reported ~10% of eligible orders) |
| Top-of-book only | IBKR paper simulates against top of book, no deep-book access; stops/complex orders are simulated (IBKR campus list relayed by https://pickmytrade.io/help/tws/tws-paper-fills-differ-live/ and https://blog.traderspost.io/article/broker-paper-trading-comparison) |
| Limit order fills too generous | r/algotrading commenter (via mirror): limit orders may never fill live but always fill on paper (https://pol1.lr.ggtyler.dev/r/algotrading/comments/1jtvi38/first_time_making_a_bot_and_running_every_day_on) |
| Missing broker-side rejections | Concretum: paper accepted opposing MOC orders on the same symbol that live IBKR rejected (Error 202 "Order would cross") (https://concretumgroup.substack.com/p/operational-pitfalls-of-algo-trading) |
| Fixed/average spread in backtests | MQL5 thread: EA profitable at fixed 10-point spread lost money with variable spreads (https://www.mql5.com/en/forum/212322/page2). Fixed-spread backtests hide costs at news/rollover/session opens |
| Spread widening on news; gold thinner than EURUSD | Spread spike magnitudes vary by source (5-8 pips to "5-30+" claims; unverified, broker-specific); XAUUSD has less depth than EURUSD (https://b2broker.com/news/how-nfp-affects-trading/ and https://www.mql5.com/en/blogs/post/775565) |
| Default-fee dry-runs | Freqtrade dry-run uses lowest-tier exchange fees vs real live fees (community tutorial https://dev.to/henry_lin_3ac6363747f45b4/lesson-20-freqtrade-simulated-trading-validation-3bca) |
| Rule of thumb haircut | One source claims realistic friction cuts backtest results 30-50% for small-edge strategies (unverified; use as a sanity prior, not a fact) |
| Latency / stale data | Connection can look healthy while data stalled (Concretum); IBKR historical pacing breaks indicators silently |
| No financial consequence / behaviour | Not an engine issue, but you will not feel drawdowns in paper |

### 4.2 Calibrating a cost model from live data (recommended method; my synthesis)
1. **Log arrival state for every order**: decision timestamp, bid/ask/mid at decision (arrival price), order type/limit price, submit time, ack time, every fill (price, qty, time), final status, and quote snapshot at fill time. Keep these in an append-only store.
2. **Compute implementation shortfall** per fill: (fill price - arrival mid) x side, in bps and in multiples of the instrument's median half-spread. Add commissions/fees and, for CFDs/metals, financing/storage (IBKR charges 0.10% p.a. storage on London gold per its page).
3. **Segment** by instrument x session (Asia/London/NY/rollover) x event window (+-5 min around NFP/CPI/FOMC) x size bucket x order type (market vs marketable limit vs passive limit).
4. **Fit a simple model**: cost = half_spread(t) + k * sigma_short * sqrt(size/typical_size) + fixed; use **p75-p90** of the empirical distribution (not the mean) as the stress-test input. For passive limits, measure *fill probability and adverse selection* (price move after fill), not just price.
5. **Feed it back** into the backtester: Nautilus exposes slippage/probabilistic fill models (docs list "Fill models: slippage and probabilistic fills", https://nautilustrader.io/docs/latest/concepts/backtesting/ - details live on subpages I did not read); LEAN has configurable fee/slippage/fill models.
6. **Re-run all candidate strategies** under (a) zero-cost, (b) calibrated, (c) calibrated x 2 spreads. Kill anything that is not profitable at (c).
7. **Track a live-vs-model residual** weekly; alert if cost per trade drifts > ~1.5x model.
8. **Minimum samples**: a few dozen fills per instrument/order-type before trusting a cell; otherwise pool and widen the haircut.

### 4.3 Shadow / canary live
- Run the live engine in **shadow mode** (full pipeline, orders stopped at an `ExecutionGate` that logs "would-submit") alongside paper to catch plumbing bugs without risk.
- Then **canary**: minimum lot sizes (e.g., 1 share, 0.01 lot / micro contracts), hard daily-loss cap, one instrument at a time, human watching. Goal is measuring costs + reliability, not profit.
- Expect an explicit "paper vs micro-live" comparison report per strategy.

### 4.4 Position & order reconciliation
- On startup and every N seconds: pull open orders, executions, positions, cash from the broker; diff against local state; **trust the broker** (Concretum: "On startup, pull today's executions from the broker and compare... When the two disagree, trust the broker").
- Nautilus does this natively: startup reconciliation compares cached order/position state with venue reports; continuous checks for in-flight/open orders; IB mass status queries orders, fills with commission reports, positions; orders left working by a previous session return as external open orders; IB `PreSubmitted` maps to `ACCEPTED` (Nautilus live + IB docs, seen). A 1.229.0 fix addressed "IB disconnect reconciliation corrupting position state" (release notes via search) which shows this area is still moving.
- Tag orders with strategy/date references; always pass explicit account on every order (silent routing to default account, Concretum).
- IB average cost includes commissions, so Nautilus replays fills to reconstruct entry price (seen) - expect small P&L basis differences vs broker statements.

---

## 5. Reference architecture (solo builder, local-first)

```
 [LLM agents: Claude via API, news/web tools]      <- cloud allowed ONLY for Claude
        |  write "trade intents" (JSON: instrument, direction, conviction, horizon, rationale, expiry)
        v
 [Intent queue: local SQLite/Postgres table or files]   <- the ONLY coupling to the LLM layer
        |
        v
 [Decision/Strategy engine (deterministic, no network except market data)]
        |  proposed orders
        v
 [Pre-trade risk gate (separate process)]  -> hard limits: max position, max notional, max orders/min,
        |                                       daily loss, instrument allow-list, price-collar vs last quote,
        v                                       "paper vs live account" assert
 [OMS / execution engine: Nautilus LiveNode or custom ib_async]
        |  idempotent clientOrderId, persisted BEFORE send
        v
 [Broker adapter] <-> [IB Gateway on localhost:4001/4002]  <->  IBKR servers
        ^
 [Reconciler loop] [Heartbeat/dead-man] [Alerting] [Audit log + parquet tick/quote recorder]
```

**Principles**
- **The execution engine must run with no LLM and no internet other than broker + market data.** The LLM layer only writes intents; if Claude/the network is down, existing positions are managed by deterministic rules (stops, time exits). Intents carry an expiry; stale intents are dropped.
- **Event loop & OMS**: use Nautilus' message-bus kernel (single-threaded event loop, one LiveNode per process; ASGI with one worker; avoid hot-reload, per its live docs) or ib_async's asyncio loop. Model the order lifecycle as an explicit state machine (NEW -> SUBMITTED -> ACKED -> PARTIAL -> FILLED/CANCELED/REJECTED/UNKNOWN). Nautilus explicitly handles "unknown outcome" in-flight commands after network failure: do the same in custom code.
- **Idempotent submission**: deterministic client order id = hash(strategy_id, instrument, signal_timestamp, intent_seq). Write the order to the DB *before* sending; on restart, look up by id at the broker before resending. IB specifics: unique `client_id` per process, order-ID partition; Nautilus rejects execution client IDs that are multiples of 1000.
- **State persistence**: Nautilus supports restoring cache from an attached backing database; otherwise SQLite in WAL mode (single writer) with append-only event table; periodic snapshots. Back up to a second disk / encrypted offsite copy.
- **Scheduling**: use exchange calendars; schedule in exchange timezone (America/New_York for US equities), not server local time (DST mismatch for ~2 weeks/yr; early-close days; MOC cutoff 3:50pm ET for NYSE) - all from Concretum's list. FX/metals: 24x5 with daily ~5pm ET rollover and thin liquidity at the Sunday open; handle swap/financing timing.
- **Monitoring/alerting**: heartbeat file/endpoint checked by a *separate* watchdog; alerts for: process down, broker disconnected, data stale > threshold, position mismatch, order reject streak, daily loss limit, 2FA pending. Telegram/Slack bots are convenient but they are external services (not LLMs); for strict local-first use a self-hosted push channel (e.g., ntfy) plus email as a fallback (suggestion, not researched). Alert content must never include keys.
- **Secrets**: macOS Keychain (or 1Password CLI/sops+age) injected at process start; separate credentials and **separate processes/containers for paper and live**; read-only/market-data keys for research jobs; assert expected account id and port at startup (IB paper 4002/7497 vs live 4001/7496) and refuse to run if mismatched. Never commit `.env`.
- **Kill switch (layered)**: (1) software flag file checked before each submit; (2) risk gate auto-trips on loss/rate/stale-data; (3) "flatten and halt" command callable from phone; (4) **broker-side protective stops/OCO** so a dead process does not leave naked risk (note Nautilus IB docs: IB does not cancel bracket exits when another order closes the position, so non-reduce-only exits can open an opposite position); (5) manual: IBKR mobile/TWS to cancel all. Nautilus' live docs I read do **not** describe a kill switch (closest: `shutdown_on_error=True`), so build it yourself.
- **Logging/audit**: structured JSON logs; append-only decision log linking *intent -> risk decision -> order -> fills*; store the LLM prompt/response hash and the data snapshot that produced each intent (for post-mortems and records).
- **Containerization**: Docker for IB Gateway (see Local-first section) and for the engine; pin image/library versions (Nautilus has breaking changes and a v1/v2 split; IB Gateway protocol >= 213 required by the adapter).
- **Failure modes to design for**: API outage / Gateway disconnect (reconnect with backoff; reconcile on reconnect), duplicate orders (idempotent ids; never blind-retry a submit with unknown outcome), stale data (per-symbol last-update watchdog), pacing violations (single queue for historical requests), clock drift (NTP monitoring), runaway loop (max orders/min, max open orders - Knight Capital's SEC order cited missing pre-submission controls and weak code-deployment governance, https://www.sec.gov/news/press-release/2013-222), wrong account/mode (assertions), corporate actions/splits and contract rolls, partial fills leaving odd lots, rejected orders (e.g., no short availability, margin), weekend gaps, version upgrade breakage (Nautilus IB doc warns about instrument-ID and magnified-contract changes across versions: flatten/cancel/clear cache before upgrades).

---

## 6. LOCAL-FIRST STACK (new constraint)

### 6.1 What "local" means for live trading
Backtests, paper and live order management all run on your own hardware. Network dependencies shrink to: **the broker's servers**, a **market-data source**, and (optionally) the Anthropic API for the *research/intent* layer, which is outside the order path.

| Component | Local? | Notes |
|---|---|---|
| Strategy/backtest engine | Yes | NautilusTrader (`pip`, wheels for Linux x86_64/ARM64, macOS ARM64, Windows) or LEAN CLI (Docker) |
| Broker connectivity | Local process talking to broker cloud | IB Gateway/TWS runs on your machine and connects out to IBKR; your code connects to `127.0.0.1` |
| Paper trading | Local simulation or broker paper | LEAN has a local paper brokerage on live data; IBKR/Alpaca/OANDA paper run on broker servers but are driven from your box |
| Hosted bots to avoid | No | QuantConnect Cloud nodes, TradingView-hosted webhooks, Lumibot's BotSpot cloud, MT5 hosted VPS |
| Data | Mixed | Cache everything to local Parquet; vendor feeds (IBKR, Databento - Nautilus has a stable Databento adapter) are not LLMs so are compatible with the rule; record your own tick/quote stream |
| Alerts | Mixed | Telegram/Slack are cloud services but non-LLM; use a self-hosted alternative if you want zero third-party dependency |

### 6.2 Recommended local components
- **NautilusTrader** as the engine (research -> paper -> live), runs entirely on the user's machine; or **LEAN CLI** if OANDA or an existing LEAN algo ecosystem matters (needs Docker; likely a Researcher seat for local live).
- **IB Gateway (not full TWS)** for headless operation. Containerized option: `gnzsnz/ib-gateway-docker` (1.3k stars; Docker image running IB Gateway/TWS with IBC + Xvfb; **aarch64 supported since 10.37.1l / 10.39.1e incl. M1/M2/M3 Macs**, but the TWS image on ARM "may have unexpected bugs"; `TRADING_MODE` paper/live/both with live->4001, paper->4002; `AUTO_RESTART_TIME` to avoid daily 2FA) (https://github.com/gnzsnz/ib-gateway-docker, seen).
- **Gateway lifecycle risk (important):**
  - IBKR designed TWS/Gateway to restart daily; since version 974 there is an auto-restart option (IBKR docs via search; page itself returned 403 for me).
  - **IBC was retired and archived 2026-09-01**; final/interim releases may still appear but "will not be actively supported". Since gnzsnz and most community setups wrap IBC, you are inheriting a dependency whose upstream is frozen (README, https://github.com/IbcAlpha/IBC, seen). You can still fork it. Mitigations: pin versions, keep the Gateway version IBC last supported, rely on IBKR's native auto-restart where possible, and design the system to tolerate a human re-auth.
  - IBC "cannot complete logins that require a physical card or device code" and cannot work with the self-updating TWS (Gateway has no self-update, so it is fine). 2FA via IBKR Mobile still needs the phone; a 2026 write-up says fully unattended startup is not possible without mobile approval (https://dev.to/xqliu/how-i-built-a-live-momentum-strategy-on-interactive-brokers-using-python-2026-26co, secondary). One 2024 Reddit-mirror comment said a nightly IBC login ran ~8 years until IBKR changed its login flow (https://redlib.hbubli.cc/r/algorithmictrading/comments/1fq2jhn/do_people_use_ikbr_here/lpalwp0).
  - **Practical plan**: assume a re-auth roughly weekly (Sunday is commonly reported); have the system alert you ("2FA needed") and **fail safe** (no new entries) until the session is back; ensure broker-side stops exist during any outage.
- **Alternative with less moving parts:** IBKR Client Portal Web API (REST) avoids the Java Gateway but has its own session-keepalive and pacing (50 req/s global per session; 10/s via CP Gateway per differing docs; 1 req/5s on some endpoints) - not evaluated as a Nautilus path.

### 6.3 Uptime: laptop/Mac vs always-on box vs VPS
| Option | Pros | Cons / failure modes |
|---|---|---|
| **Daily-driver MacBook** | Zero cost, convenient | Sleeps, lid close, Wi-Fi drops, macOS update reboots, you travel; **not suitable for unattended live** beyond micro-live supervised sessions |
| **Mac mini (Apple Silicon) always-on at home** | Silent, low power, native macOS, Docker works, runs ARM Nautilus wheels and ARM IB Gateway image | Needs: `pmset sleep 0`, auto-restart after power failure (`pmset autorestart 1`; macOS 26.5 added a GUI toggle "Start up automatically after a power failure" per community guides; one M4 mini user reported pmset autorestart keys not working - verify with `pmset -g`), auto-login + LaunchAgents/`launchd KeepAlive`, **disable automatic macOS update reboots** or schedule them (a home-server write-up found a mini sitting at the login screen with services dead after an update restart), UPS with graceful shutdown, second internet uplink/phone hotspot, Wake/Remote access (Tailscale-style). Residential ISP/power outage = downtime |
| **Small Linux mini-PC at home** | Cheapest always-on, headless-friendly, systemd restarts | Same power/ISP issues; no macOS-only tooling needed since everything is Python/Docker |
| **Low-cost VPS you control** (Linux x86_64 or ARM64) | Datacenter power/network, static IP, can sit near broker; Nautilus wheels for Linux x86_64/ARM64; IB Gateway via Docker+Xvfb is a common pattern (https://newyorkcityservers.com/blog/interactive-brokers-vps-tws-ib-gateway, vendor) | Not "on your machine" but still under your control; you hold the 2FA phone; IB login from a new IP may trigger extra prompts (unverified); lock down SSH/Tailscale; keys on a remote host; costs money |
| **Hybrid (recommended)** | Research/backtests + Claude agents on the Mac; **execution engine + Gateway on an always-on box/VPS**; Mac only sends intents (via SSH/rsync/DB replication) | One more thing to deploy; intents channel must be authenticated |

Operational checklist for a Mac/mini: `caffeinate`/`pmset` settings (verify per macOS build), launchd plist with `KeepAlive`, log rotation, disk-space alerts, daily `pmset -g log` review, time sync, firewall allow-list, FileVault vs auto-login trade-off (FileVault blocks unattended boot-to-login after power loss: decision needed), nightly encrypted backups of the state DB and logs.

### 6.4 Keeping the engine running with no LLM/network dependency but the broker
- Intents are **data**, not commands: the engine accepts a validated schema only; unknown fields ignored; max N intents/hour; each with expiry. A prompt-injected or hallucinated intent still has to pass the risk gate (instrument allow-list, notional caps, price collar).
- The engine's *protective behaviour* (stops, time stops, flatten-by-time, max daily loss) is entirely rule-based and local.
- Market-data stale watchdog and broker heartbeat trigger "reduce-only" mode.
- Local LLM is not required for execution. (Other tracks cover local models.)
- Cache required reference data locally (calendars, contract specs, holidays) so a cold start does not depend on a web call.

---

## 7. Staged go-live process and gates

Gate numbers below are **my synthesized recommendations** (not from a single authoritative source). The Freqtrade community examples I saw recommend 1-2 weeks of dry-run and "dry-run performance >50% of backtest" before live (https://dev.to/henry_lin_3ac6363747f45b4/lesson-22-freqtrade-pre-live-trading-checklist-1i8e) - treat those as minimums for crypto bots, not for multi-asset systems.

| Stage | Purpose | Duration (guideline) | Gate to advance |
|---|---|---|---|
| 0. Research backtest | Find candidate edge on vectorized tool; strict point-in-time data, no look-ahead, realistic costs | - | Edge survives (a) calibrated-cost model x2 spreads, (b) parameter neighbourhood stability, (c) multiple-testing awareness (record how many variants were tried; consider deflated Sharpe/PBO methods, from Lopez de Prado literature - not re-verified) |
| 1. Event-driven backtest in the *live engine* | Same code path as live; surfaces order-handling bugs | - | Results match vectorized prototype within tolerance (e.g., P&L/trade count within ~5-10%) or differences explained |
| 2. Walk-forward / out-of-sample / regime split | Check decay | Rolling windows, e.g. train 2-3y/test 6m | OOS Sharpe/expectancy > 0 after costs in a majority of windows; no single window explains the result; max drawdown within budget |
| 3. Shadow (live data, no orders) | Verify data feed, signal timing, latency, stale-data handling | 1-2 weeks | Zero unexplained signal differences vs offline recompute on recorded data |
| 4. Paper (broker paper) | Test OMS, reconciliation, restarts, rejects, 2FA/restart events | >= 4 weeks and covering a news-heavy window (NFP/FOMC/CPI) and at least one forced restart + one disconnect | 100% reconciliation matches; no duplicate orders; all kill-switch paths tested; alert latency < target; paper P&L within a wide band of model (don't over-trust) |
| 5. Micro-live (canary) | Measure real costs/fill quality; psychological check | >= 4-8 weeks or N >= 30-50 round trips per strategy, whichever is longer | Realized cost per trade <= 1.5x calibrated model; live-vs-backtest tracking error explained; zero operational incidents of severity "wrong position" |
| 6. Scaled live | Increase risk gradually | Step size e.g. +25-50% only after each month at target gate | Pre-defined stop rules: pause at X% drawdown or Y sigma below expected; position/notional caps tied to risk budget (Track 5) |
| Always | Change control | - | Any code/model change returns the strategy to stage 3 (Knight Capital: governance on code deployment was a cited failure, SEC press release 2013-222) |

Process notes from practitioners (secondary): HN commenter "bproctor" (six years on an algo system): the backtesting and broker plumbing is the easy part; strategy discovery takes most of the effort (https://news.ycombinator.com/item?id=44810552). Another commenter with a crypto business: latency and tail behavior matter, and the work is stressful.

---

## 8. Regulatory / tax / compliance awareness (not legal advice; jurisdiction-dependent)

**US pattern day trader rule - status as of 2026-11-14 (verified via FINRA):**
- FINRA Regulatory Notice 26-10: new intraday margin standards replace day-trading margin requirements "in their entirety"; the day-trade-count PDT designation and the $25,000 minimum equity requirement are removed. **Effective 2026-06-04**; members needing time may phase in over up to 18 months, **until 2027-10-20**. New Rule 4210(d)(2): firms compute an intraday margin deficit on days with intraday-margin-level-reducing transactions; repeated unmet deficits can lead to a 90-day restriction. Portfolio-margin $5M threshold preserved. (https://www.finra.org/rules-guidance/notices/26-10). SEC approval 2026-04-14 per multiple secondary sources (e.g., https://www.thinkadvisor.com/amp/2026/04/14/sec-approves-plan-removing-day-trading-limit-for-small-investors/). Some brokers state a $2,000 margin minimum (E*TRADE summary, secondary). **Check your specific broker's go-live date for the new regime.** (Forex and futures were never subject to the equities PDT rule: general knowledge, unverified here.)

**Leverage limits:**
- EU/EEA (ESMA product-intervention, 2018; later adopted nationally, and UK FCA aligned): retail CFD leverage 30:1 majors, 20:1 non-major FX/gold/major indices, lower for others; negative balance protection; 50% margin close-out; standardized risk warnings; opt-up to "professional" possible (https://www.esma.europa.eu/press-news/esma-news/esma-adopts-final-product-intervention-measures-cfds-and-binary-options). I did not verify post-2018 permanent status or silver/commodity tiers.
- US retail forex (CFTC/NFA): 50:1 majors, 20:1 minors; FIFO rule; brokers must be NFA/CFTC-registered (secondary sources: https://brokerchooser.com/safety/leverage-margin-limits-us, https://topbrokers.com/forex-basics/laws-and-limits-of-forex-trading-in-the-us). A "10:1 precious metals" figure appears on BrokerChooser only (unverified). US retail CFDs: widely described as unavailable (unverified here).
- Important engineering implication: **FIFO and hedging restrictions in the US** can break strategies that hold opposing positions or close specific lots. Test order-handling against these rules in the paper/micro stage.

**Algo trading legality (retail):** Generally permitted via broker APIs in the US/UK/EU/much of Asia, subject to broker terms. India requires broker/exchange pre-approval and registered strategies for retail algos (HN comment context only; verify). Market-access rule 15c3-5 applies to broker-dealers (not individuals), but your broker's risk checks and terms apply to you.

**Tax and records (US-centric, secondary sources; ask a tax professional):**
- Wash-sale rule (IRC 1091) applies to stocks/securities (including ETFs) - 30 days before/after; **not** generally to Section 1256 contracts (regulated futures) or retail spot forex; Schwab and others summarize (https://www.schwab.com/learn/story/year-end-tax-trading-wash-sales-and-more). An algorithm that churns the same ticker across accounts can create wash sales automatically - **track tax lots and wash-sale adjustments across all accounts including IRAs**.
- Retail spot forex defaults to Section 988 (ordinary gain/loss); an election to 1256-style treatment has timing/eligibility conditions that sources disagree on (https://daytradingtoolkit.com/day-trading-basics/forex-trading-tax-section-988-vs-1256).
- Physical-metal ETFs (GLD/SLV) may be taxed as collectibles at up to 28% long-term; futures-based commodity funds may differ (secondary).
- CME futures (MGC/SIL) are Section 1256: 60/40 treatment, mark-to-market at year end (secondary).
- Record keeping: keep immutable logs of orders, fills, statements, FX rates, data snapshots and strategy versions for at least the statutory retention period in your country (often 5-7 years; verify). Export broker statements monthly; reconcile to your OMS.
- Other jurisdictions: tax on FX/metals and CFDs varies widely (e.g., spread-betting exemptions in the UK; CFD gains taxable elsewhere) - unresearched.

---

## 9. Community findings

**Reachability:** `reddit.com`/`old.reddit.com` were blocked for direct fetch in this environment; web search returned Reddit mirrors (redlib/libreddit instances) and forum threads instead. Hacker News was reachable via the Algolia API. I did not reach YouTube, X, or Instagram in this pass (not searched/fetched), so nothing here represents those platforms.

- **NautilusTrader on HN (208 pts, 127 comments, 2025-08-06):** little hands-on live-trading feedback. Notable: a quant-firm commenter said Nautilus has its own OMS that may not match the broker's (e.g., IBKR's), so integration is the tricky part and it is better as a bootstrap than a finished solution; another praised the Risk Engine's completeness but cautioned regulated automated trading is hard to make plug-and-play; skeptical commenters said retail intraday algos rarely beat buy-and-hold. https://news.ycombinator.com/item?id=44810552
- **No substantial r/algotrading threads with hands-on Nautilus live complaints surfaced**; one thread notes a user used QuantConnect for a year ("powerful, but definitely has a learning curve") and then wrote their own engine; another mentions a lack of Nautilus learning resources in one regional forum and AI assistants as the main teachers (mirror: https://libreddit.winscloud.net/r/algotrading/comments/1m1d68g/is_my_custom_trading_engine_good/n3hiw2h/).
- **IBKR + IBC pain:** the 2024 comment about IBC auto-login breaking after IBKR changes (link in 6.2); ElliteTrader thread "IB is forcing 2FA" (https://elitetrader.com/et/threads/call-for-action-ib-is-forcing-2fa.370312/post-5695818); QuantConnect forum posts on IB Gateway soft-restart timeouts and 2FA Sunday prompts (https://www.quantconnect.com/forum/discussion/16028/the-ibgateway-soft-restart-timed-out/, https://www.quantconnect.com/forum/discussion/19234/new-problem-starting-live-algo-with-ib-gateway/). Concretum's ten IBKR operational pitfalls (stale data, Error 202, pacing, MOC cutoffs, early closes, clock drift, default-account routing, reconciliation, paper-vs-live, DST): https://concretumgroup.substack.com/p/operational-pitfalls-of-algo-trading
- **Paper vs live:** r/algotrading commenters (mirror 2025): limit orders always fill on paper but may not live; Alpaca paper spreads decent for liquid names, worse for illiquid; Alpaca forum threads on multi-minute paper fill delays (https://forum.alpaca.markets/t/paper-trading-fill-delays-of-50-260-seconds-limit-orders-filled-minutes-after-price-crossed/18223). "Why your massive gains in backtesting aren't real" thread (https://redlib.ssps.io/r/algotrading/comments/1lbl5lb/why_your_massive_gains_in_backtesting_arent_real).
- **MT5 on Mac:** repeated MQL5-forum threads confirming no native macOS/ARM Python package (https://www.mql5.com/en/forum/478849, https://www.mql5.com/en/forum/425741).
- **Tradovate API cost surprises:** funded account + ~$25/mo API + CME data agreement; community thread "Is CME sub-vendor requirement for API access $290 per month" (https://community.tradovate.com/t/is-cme-sub-vendor-requirement-for-api-access-is-290-per-month/6215) - figures unverified.
- **"Brokerages Suck: Navigating the Challenges of Live Algo Trading"** (Medium, general complaints about broker APIs; I did not read it fully): https://medium.com/@codingandcoffee/brokerages-suck-navigating-the-challenges-of-live-algo-trading-743b47f6401e
- **Popular combos found in the wild (anecdotal):** IBKR + Python (ib_async/ib_insync) for equities/futures; Alpaca for US equity bots; MT5 EAs for retail FX/gold; OANDA v20 for FX scripts; LEAN + IBKR/OANDA. I could not reliably quantify prevalence from the sources reachable.

---

## 10. Repos and links (quick list)
- NautilusTrader: https://github.com/nautechsystems/nautilus_trader ; docs https://nautilustrader.io/docs/latest/ ; IB: https://nautilustrader.io/docs/latest/integrations/interactive_brokers/ ; live: https://nautilustrader.io/docs/latest/concepts/live/ ; PyPI https://pypi.org/project/nautilus-trader
- LEAN: https://github.com/QuantConnect/Lean ; CLI https://github.com/QuantConnect/lean-cli ; brokerages https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages.md ; pricing https://www.quantconnect.com/pricing.md
- vectorbt: https://github.com/polakowo/vectorbt ; PRO https://vectorbt.pro/
- backtrader: https://github.com/mementum/backtrader ; Backtesting.py https://github.com/kernc/backtesting.py ; bt https://github.com/pmorissette/bt ; zipline-reloaded https://github.com/stefan-jansen/zipline-reloaded ; PyBroker https://github.com/edtechre/pybroker
- Lumibot: https://github.com/Lumiwealth/lumibot ; OpenAlgo: https://github.com/marketcalls/openalgo
- Crypto-centric reference: https://github.com/freqtrade/freqtrade ; https://github.com/jesse-ai/jesse ; https://github.com/hummingbot/hummingbot
- IB: ib_async https://github.com/ib-api-reloaded/ib_async ; IBC (archived) https://github.com/IbcAlpha/IBC ; Docker gateway https://github.com/gnzsnz/ib-gateway-docker ; IB Gateway docs https://www.interactivebrokers.com/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway
- Brokers: OANDA v20 https://developer.oanda.com/rest-live-v20/introduction/ ; Alpaca paper https://docs.alpaca.markets/docs/paper-trading ; alpaca-py https://github.com/alpacahq/alpaca-py ; Saxo environments https://www.developer.saxo/openapi/learn/environments ; cTrader Open API FAQ https://ctrader.com/faq/open-api ; Capital.com API https://open-api.capital.com/ ; IG API https://www.ig.com/uk/trading-platforms/trading-apis ; IBKR metals commissions https://gdcdyn.interactivebrokers.com/en/pricing/commissions-metals.php
- Regulation: FINRA 26-10 https://www.finra.org/rules-guidance/notices/26-10 ; ESMA https://www.esma.europa.eu/press-news/esma-news/esma-adopts-final-product-intervention-measures-cfds-and-binary-options

---

## 11. Recommended stack (given local-first, unknown jurisdiction)

**Core (default recommendation)**
1. **Research:** vectorbt OSS (fast sweeps) + your own data store (Parquet). Optionally PyBroker/bt for walk-forward/allocation studies.
2. **Engine:** **NautilusTrader** for event-driven backtest -> paper -> live. Start on stable **1.231.x**; plan the v2 migration deliberately (use a pinned env, test on v2 RC only in backtest/paper). Fallback: **LEAN CLI** locally if you need OANDA or prefer its maturity.
3. **Broker:** **Interactive Brokers** for stocks + FX + spot gold/silver (or MGC/SIL futures) with the paper account first. Single broker minimizes adapter risk. Keep an OANDA or Saxo account as a *later* second venue only if you write/accept a custom adapter or use LEAN.
4. **Gateway:** IB Gateway in Docker (gnzsnz image) on an always-on Mac mini/mini-PC/low-cost VPS; native IBKR auto-restart; accept weekly 2FA; alert on auth loss; broker-side stops.
5. **Safety layer you must write:** deterministic risk gate, idempotent order ids, reconciliation loop, kill switch, heartbeat/dead-man, audit log.
6. **LLM boundary:** Claude agents (cloud) -> intents table -> deterministic engine. No LLM in the order path or the risk gate.
7. **Calibration loop:** log arrival-price vs fills from micro-live; feed back to backtest cost model monthly.

**Avoid / defer:** backtrader (unmaintained), MT5-Python (Windows-only), OpenAlgo (India), hosted bot platforms, FXCM API (status unclear), Alpaca for FX/metals (not offered), CFD brokers if you are in the US.

---

## 12. Open questions for the user
1. **Country/tax residency** (decides: CFD availability, leverage caps, which IBKR entity/metals product, OANDA/Saxo/IG/Capital.com eligibility, tax treatment, algo registration rules).
2. Account size and risk budget (affects micro-lot feasibility, commission minimums, margin type).
3. Target holding period/frequency (intraday FX vs daily swing changes latency, data and cost-model needs; and whether LLM-driven signals are even fast enough to matter).
4. Which gold/silver instrument is acceptable: spot via IBKR, CME micro futures, CFDs, or ETFs?
5. Is an always-on machine available (home mini/mini-PC) or is a small VPS acceptable? Who can approve IBKR Mobile 2FA when you travel?
6. Appetite for writing a custom adapter (OANDA/Saxo for Nautilus) versus accepting IBKR-only?
7. Is Telegram/Slack acceptable as a non-LLM cloud service for alerts, or must alerts be self-hosted?
8. Preferred license posture: LGPL (Nautilus), GPL (Lumibot/backtrader), AGPL (Backtesting.py, OpenAlgo) have different implications if you ever distribute or offer this as a service.
9. Should the platform later support crypto (then Freqtrade/Hummingbot-style connectors and Nautilus' many crypto adapters become relevant)?

## 13. Things I could not verify (explicit)
- IBKR spot-FX commission and account minimums; Tradier/Capital.com/IG/Saxo fees and minimums; OANDA rate limits and current XAU spreads; zipline-reloaded stars/license; backtrader fork health; Backtesting.py and zipline live support; Jesse/Hummingbot paid features and internals; whether QuantConnect's local live strictly requires a paid seat (staff reply seen only via search summary); IBKR's own paper-trading limitations page (I relied on third-party relays); current status of ESMA measures beyond 2018 and exact US metals leverage; any YouTube/X/Instagram content.
