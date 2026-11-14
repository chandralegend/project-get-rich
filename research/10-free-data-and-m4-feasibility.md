# 10 - Free Data Stack and Apple M4 16 GB Feasibility

Date: 2026-11-14. Track: (A) free data for Binance + MT5-traded instruments, (B) what runs locally on an M4 with 16 GB. Engineering research, not legal, tax or investment advice.

**Evidence tags used throughout**
- **[V]** = I fetched or probed it myself in this session (2026-11-14); URL given.
- **[S]** = search-result snippet or third-party summary; not confirmed on a primary page.
- **[A]** = my own arithmetic; the assumptions are stated next to it.
- **[U]** = from memory or not confirmed; check before relying on it.

Reddit, X, Instagram and TikTok were not reachable for any agent so far; I did not try to get around that. Nothing below comes from them.

---

## 0. TL;DR

1. **Free data is enough to research crypto and FX/metals at 1-minute resolution.** Binance bulk files, the Binance REST API, Dukascopy, HistData, CFTC, ECB, Fed/ECB/BoE/BoJ RSS and a Forex-Factory-style JSON calendar all worked from this machine today. Tick-level crypto history is the one thing that is not practical (see sizing).
2. **New licence trap on Binance's bulk archive.** The `data.binance.vision` terms file was added to the repo on 2026-09-30 (header says "Last Updated August 26, 2026"). It licenses the archive under **CC BY-NC-SA 4.0**, allows "algorithmic historical backtesting for purely personal non-production research", and **§4.2 says you shall not use the Datasets "for live proprietary trading execution"** [V]. §2.4 says models and indicators derived from the data are governed by the same terms. A personal bot trained on Vision files and then trading live is at best a grey area. Safer pattern: build the *training* set from the REST API (`/api/v3/klines`, 1000 bars per call, weight 2, 6000 weight/min) and use Vision only for research you do not deploy, or ask Binance. I did not find the API terms' position on market-data use, so that is open.
3. **Gold and silver now trade on Binance.** `fapi/v1/exchangeInfo` lists `XAUUSDT` and `XAGUSDT` as `TRADIFI_PERPETUAL` (onboarded 2025-12-11 and 2026-01-07) among 237 TradFi perps (copper, oil, gas, equities) [V]. History is under a year, but it is the only free route that has the exact execution venue's prices for metals on Binance.
4. **Survivorship bias is partly fixable for free.** Vision still holds delisted symbols (LUNAUSDT, FTTUSDT, SRMUSDT, LUNCUSDT present) and 3,770 spot / 1,081 USD-M futures symbol folders [V]. The trap is picking "today's top 20" as your universe.
5. **M4 16 GB reality.** Metal's default GPU working-set cap is about 10.9 GB on a 16 GB Mac [V, mlx-lm issue #644]. Usable for models: roughly 8 GB on a box that also runs DuckDB, a crawler and Python; 10.9 GB if nothing else is running. 4B to 9B models at 4-bit fit. gpt-oss-20b (14 GB) and anything 14B+ do not co-reside.
6. **Local LLM is not a cost play any more.** Claude Haiku 5.5 costs $0.10 / $0.50 per million input/output tokens [V, pricing page], about $1.75 per 10,000 articles (1,000 tokens in, 150 out each) [A]. A local 4B model manages about 400 such articles per hour at full duty, a 9B about 200 [A, from a verified llama.cpp M4 benchmark]. Use local for **embeddings, dedupe, sentiment, cheap triage** and for resilience; send extraction backlog, synthesis and judging to Claude.
7. **Claude monthly bill for personal use: about $27 (lean) / $69 (central) / $175 (heavy)**, arithmetic in section 6 [A].
8. **The machine this research ran on reports itself as a Mac mini (Mac16,10), Apple M4, 16 GB, 228 GiB SSD with about 47 GiB free** [V, `system_profiler`, `df`]. If that is your trading box, **disk is a tighter constraint than RAM**; plan an external SSD for any archive beyond about 15 GB. I cannot confirm it is your machine.

---

## 1. Free data source table

History and limits are what I saw on 2026-11-14 unless tagged otherwise. "Local bulk?" = can you download once and keep a full local copy.

### 1a. Crypto

| Source / asset | History | Limits seen | Licence / ToS | Local bulk? |
|---|---|---|---|---|
| **Binance Vision** spot `klines` (1s to 1mo), `aggTrades`, `trades` [V] | BTCUSDT 1m from 2017-08; 1s klines also from 2017-08; daily files appear next day (latest UM daily kline was 2026-11-13) | Static files, no API key. Each zip has a `.CHECKSUM`. **From 2025-01-01 spot timestamps are microseconds**, earlier ones milliseconds. README lists two archive corrections (2022-04-21 agg trades, 2022-08-08 klines) | **CC BY-NC-SA 4.0 plus §4.2 "no live proprietary trading execution"; derived models covered (§2.4); non-commercial; ShareAlike on redistributed derivatives** [V, TERMS_AND_CONDITIONS.md] | Yes |
| **Binance Vision** USD-M futures: `klines`, `markPriceKlines`, `indexPriceKlines`, `premiumIndexKlines`, `aggTrades`, `trades`, `fundingRate`; daily-only `metrics`, `bookDepth`, `bookTicker` [V, S3 listing] | BTCUSDT futures 1m from 2020-01; `fundingRate` monthly from 2020-01; `metrics` (open interest + long/short ratios, 5-min, 289 rows/day) from 2020-09; `bookDepth` from 2023-01 | `metrics` columns: sum_open_interest(_value), toptrader and global long/short ratios, taker long/short volume ratio [V, sample file]. Monthly `bookTicker` 404 for BTCUSDT 2026-09 | Same terms as above | Yes |
| **Binance Vision** `option/daily`: `BVOLIndex`, `EOHSummary` [V] | not probed | | Same | Yes |
| **Binance REST** spot and futures [V] | Klines: no documented lookback limit; 1000 bars per call (futures 1500 max), spot weight 2. Spot limit 6000 weight/min/IP [V, `exchangeInfo`] | Funding history 1000 rows per call. **Open interest history, basis and long/short ratio: latest 30 days only** [V]. Futures `aggTrades` window under 1 h, summary said "past 48 hours"; I did not test this | API terms of use not found in this session [U] | Backfill 5 years of 1m for 20 symbols = 2,628 calls x 20 x weight 2 = 105,120 weight, about 18 minutes of full budget [A] |
| **Binance WebSocket** `forceOrder` (liquidations) [S] | Live only; **no historical liquidation files in Vision** (probed `liquidationSnapshot` prefixes, empty) | Snapshot stream: only the latest liquidation per symbol per 1000 ms is pushed, so counts are under-reported [S, Binance docs via search] | | You must record it yourself |
| **Binance announcements** (listings, delistings, futures launches) [V] | Undocumented JSON endpoint `.../bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=48` returned 2,294 "New Cryptocurrency Listing" articles | Undocumented, can change or block | Unknown | Poll and store |
| **Coinbase Exchange** public candles [V] | `/products/BTC-USD/candles?granularity=60` worked without a key | About 300 candles per call [U] | Public API; ToS not read | Backfill is possible; slow |
| **Kraken** public OHLC [V] | `/0/public/OHLC?pair=XBTUSD&interval=1` worked | Roughly 720 recent candles only [U], so not a deep 1m history | ToS not read | Recent only; use trades endpoint for more |
| **Deribit** public API [V] | DVOL (implied vol index) hourly data returned for 2026-01-01 | Rate limits not read | ToS not read | Yes (small) |
| **CoinGecko Demo (free)** [V, pricing.md] | Daily and hourly: 1 year; 5-minute: 1 day | 100 calls/min, 10,000 call credits per month | **Attribution required; commercial use not included** | Poor: 1-year cap |
| **DefiLlama** `api.llama.fi` [V] | `/protocols` answered without a key | Docs page I tried 404'd; rate limits and pro-only endpoints not verified | Not read | Yes (TVL, stablecoins) |
| **Fear and Greed (alternative.me)** [V] | `/fng/?limit=2` returned 13 "Extreme Fear" for 2026-11-14 and 20 for the day before | Rate limit and attribution terms not read | Not read [U] | Yes (daily, small) |
| **Coinalyze** (OI, funding, liquidations aggregates) [S] | Docs page fetch returned only the tagline "Free crypto data API" | Key, rate limit and retention not confirmed | Not read | Unknown |
| **Glassnode / CryptoQuant / CoinGlass free tiers** | not checked | | | Treat as unverified; free tiers are usually daily-only and delayed [U] |

### 1b. FX, metals, indices

| Source / asset | History | Limits seen | Licence / ToS | Local bulk? |
|---|---|---|---|---|
| **Dukascopy** historical export + `dukascopy-node` (MIT) [V] | Page says "Forex, Commodities and Indices", tick-by-tick to monthly, CSV. `dukascopy-node` lists XAUUSD from 1999-06-03; track 02 counted 290 forex instruments | **dukascopy-node may need a headless Chromium to get an AWS WAF token; a plain 403 stops the download** [V, README]. The WAF is a sign they police automated pulls | **No data licence text on the export page; disclaimer page does not address copying or reuse** [V]. Treat as personal-use-only by prudence | Yes, slowly; keep request rate low |
| **HistData.com** [V] | 1-minute bars and ticks, 66 free forex crosses; XAU/USD from 2009-03, XAG/USD 2009-05, EUR/USD 2000-05, indices 2010-11 | **Time is Eastern Standard Time with no DST** (fixed UTC-5). Monthly zip files by pair. FTP/auto-update are paid ($7/month/format) | "Use the data at your own will and risk"; personal use and redistribution not addressed | Yes (manual or polite scripting; automation permission unclear) |
| **MT5 broker history** | Whatever the broker server keeps; Python/EA can only read what the terminal holds, governed by "Max bars in chart" [V, MQL5 docs]. One forum user got only about 3 months of 1-minute bars until they fixed that setting and restarted the terminal [V, forum 490426] | Docs say returned time is UTC; many forum posts say broker server time [S/U]. **Test with a known event** (e.g. US CPI release) before trusting it. The official `MetaTrader5` Python package is reported Windows-only [S]; options are Wine, a Windows VM/VPS, a third-party Docker/Wine wrapper (`siliconmetatrader5`, supply-chain risk), or an MQL5 script that writes CSV from inside the terminal | Broker's terms | Yes, but only to the depth the broker offers. **This is the data that matters for costs and fills (track 02)** |
| **Binance TradFi perps** `XAUUSDT`, `XAGUSDT`, 237 others [V] | From 2025-12-11 / 2026-01-07 (Vision monthly 1m files start 2025-12) | Same API limits as other futures | Same Vision terms | Yes |
| **PAXG / XAUT** gold-backed tokens [V, listed in exchangeInfo / Vision] | PAXGUSDT in Vision spot and futures; XAUTUSDT perp onboarded 2026-03 | Tracks gold only approximately | Same | Yes |
| **Stooq** [V] | `q/d/l/?s=xauusd&i=d` returned a "requires JavaScript to verify your browser" page, not CSV | I did not try to bypass this | Not read | **Not usable by a plain script today** |
| **LBMA gold price** [V] | `prices.lbma.org.uk/json/gold_pm.json` returned a challenge HTML page | Not bypassed. Track 02 already noted FRED dropped LBMA fixes in 2022 | | Not usable by script today |
| **FRED** | API host answered `400` to a call with a dummy key (so a free key is needed); the keyless `fredgraph.csv` URL failed to connect from this machine (HTTP 000, cause unknown) [V] | I could not confirm the 120 requests/min figure [U]. ALFRED (vintage history) exists per the FRED site menu [V] | Terms say third-party series may carry their own copyright [U] | Yes with a key |
| **ECB data API** [V] | EUR/USD reference rate 1.1081 for 2026-11-12 returned as CSV | Keyless | Public | Yes |
| **BoE, BoJ, Fed, ECB press RSS** [V] | All returned RSS XML today | Keyless | Press content; check reuse terms before redistributing | Poll and store |
| **CFTC COT** [V] | Historical zips: legacy from 1986, disaggregated and TFF from 2009/2010, per-year files to 2026; `f_disagg.txt` latest (report date 2026-11-03 seen); Socrata API `publicreporting.cftc.gov/resource/72hh-3qpy.json` answered | Weekly, published after Tuesday data date (publication lag: store both dates) | US government data | Yes |
| **SEC EDGAR** [V] | Bulk and APIs free | Max 10 requests/s, must send a User-Agent with contact email; "download only what you need" | Public | Yes |
| **Stocks/indices** (yfinance etc.) | Track 02 covers this. yfinance is personal-use-only per its README; unadjusted vs adjusted prices and silent data revisions are the usual traps [S from track 02] | | | Context only |

---

## 2. News, sentiment and calendar sources

| Source | What | Free-tier facts seen | Store + LLM use allowed? |
|---|---|---|---|
| **CoinDesk, Cointelegraph, Decrypt, The Block RSS** [V] | Crypto headlines + summary | All four returned RSS XML today | Feed terms not read [U]. Store headline, link, timestamp and short summary; avoid republishing full text |
| **FXStreet news RSS** [V] | FX and commodities | Returned RSS | Same caveat |
| **Kitco** [V] | Gold news | `/rss/` is an HTML index page, feed URLs not tested | Not tested |
| **Fed press RSS, Fed calendar JSON** (`federalreserve.gov/json/calendar.json`) [V], **ECB, BoE, BoJ RSS** [V] | Central-bank statements and meeting schedule | Keyless | Public-sector press material; check each site's reuse notice |
| **Binance announcements** [V] | Listings, delistings, futures launches; today's feed shows 2026-11-12 "Multiple TradFi USDS-M Perpetual Contracts" | Undocumented endpoint | Unknown; poll politely |
| **GDELT** [V] | DOC API returned HTTP 429 with the message "limit requests to one every 5 seconds"; project suggests ngrams or GKG files for volume. GDELT 2.0 events and GKG update every 15 minutes; page says "100% free and open" | Keyless | Terms of Use link not read (citation requirement unconfirmed) |
| **CryptoPanic** [S] | Aggregator with votes/sentiment | Search summary of the official page: free API, 5 requests/s, no metadata, **must link back to CryptoPanic**. My direct request got a bot-challenge page, and the page fetch returned only the title | **Storage and LLM terms not found. Treat as unverified** |
| **Economic calendar (Forex-Factory-style JSON)** `nfs.faireconomy.media/ff_calendar_thisweek.json` [V] | Title, country, impact, forecast, previous for the current week | Only the current week; undocumented mirror | ToS unknown; Forex Factory itself may forbid scraping [U]. **Snapshot it daily** so forecast revisions and actuals are timestamped |
| **FRED release calendar, BLS/BEA schedules, ECB meeting calendar** | Official schedules | Not fetched [U] | Public |
| **Fear and Greed index** [V] | Daily crypto sentiment index | See table 1a | Attribution terms unread |
| **Hacker News (Algolia API)** [V] | Tech/crypto chatter | Keyless search returned JSON | Not read |
| **Bluesky public search** [V] | Returned HTTP 403 from here | Not bypassed | n/a |
| **StockTwits** [V] | Cloudflare "Just a moment" challenge | Not bypassed | n/a |
| **Reddit, X, Instagram, TikTok** | Unreachable for all agents; not attempted. Reddit's API is restricted [per your note] | | Treat as unavailable. Replacements are RSS + announcements + Hacker News + GDELT, which give much thinner retail-sentiment coverage |

---

## 3. Storage sizing (with arithmetic)

### 3a. Measured anchors [V]

| File (zipped CSV) | Size |
|---|---|
| BTCUSDT spot 1m, one month (30 days = 43,200 rows) | 2.04 to 2.41 MB (2021-05: 2.41, 2023-06: 2.04, 2026-09: 2.05) |
| ADAUSDT spot 1m, 2026-09 | 1.60 MB |
| BTCUSDT spot 1s, 2026-09 | 70.3 MB (ETH 61.1 MB) |
| BTCUSDT spot aggTrades, 2026-09 / 2021-05 / 2023-06 | **396 MB / 1,119 MB / 318 MB** |
| ETH 337 MB, XRP 160 MB, SOL 102 MB, ADA 26 MB (aggTrades 2026-09) | |
| BTCUSDT spot `trades`, 2026-09 | 662 MB |
| BTCUSDT futures aggTrades, 2026-09 | 437 MB |
| BTCUSDT futures `metrics`, one day | 11.6 KB (289 rows, about 40 B/row) |
| BTCUSDT futures `bookDepth`, one day | 562 KB |

The 6.7 MB uncompressed CSV for one BTC month has 43,200 rows, so about 155 B/row as text and about 48.6 B/row zipped [V]. I assume Parquet with zstd lands at 25 to 40 B/row for OHLCV [A, assumption: not measured, I did not install pyarrow].

### 3b. 5-year estimate, 20 crypto and 10 FX/metal symbols

| Dataset | Rows (arithmetic) | Size assumption | Estimate |
|---|---|---|---|
| Crypto spot 1m | 20 sym x 5 yr x 525,600 min/yr (365 x 1440) = **52.56 M** | 25 to 40 B/row (upper bound, zip-equivalent 48.6) | **1.3 to 2.1 GB** (2.6 GB worst case) |
| Crypto USD-M perp 1m (same 20) | 52.56 M | same | 1.3 to 2.1 GB |
| Funding rate | 3/day x 365 x 5 x 20 = 109,500 | trivial | under 10 MB |
| Futures `metrics` (OI, ratios, 5-min) | 288/day x 365 x 5 x 20 = **10.5 M** | 30 to 45 B/row | 0.3 to 0.5 GB |
| FX/metals 1m, bid and ask stored | 10 sym x 5 yr x 374,400 bars/yr (7,200 min/week x 52) = **18.7 M** | 30 to 60 B/row | 0.6 to 1.1 GB |
| **OHLCV lake total** | | | **about 3.5 to 6.5 GB** |
| Crypto **aggTrades** (do not do this) | 20 sym x 60 months x ~120 MB (my assumed average from the five samples above, which range 26 to 1,119 MB) | assume Parquet is about the same as the zip | **about 144 GB** |
| Crypto 1s klines, 5 yr, 20 sym | BTC 70 MB/month x 60 = 4.2 GB for BTC alone | | tens of GB; keep 1s for 2 to 3 symbols and 12 months (about 2.3 GB) |
| FX ticks | assumed ~150,000 ticks/day/pair x 255 days x 5 yr x 10 pairs = 1.9 B ticks x ~10 B/tick (assumption) | tick density is an assumption, not measured | **about 19 GB**; keep 3 pairs for 2 years (about 2.3 GB) |
| News store, year 1 | assumed 3,000 deduped articles/day x 365 = 1.1 M; 5 KB text = 5.5 GB raw, about 1.5 GB zstd | | 1.5 GB |
| Embeddings, year 1 | 1.1 M x 1024-d x fp16 (2,048 B) | | 2.2 GB |

Net: **a sensible first-year footprint is about 10 to 15 GB** (lake + news + embeddings + features), versus 47 GiB free on the inspected machine. Full crypto trade history is out of reach on this disk.

### 3c. Recommended layout (DuckDB + Parquet)

```
lake/
  bronze/   raw as downloaded (zips, RSS XML, API JSON) + manifest.parquet
            (source_url, retrieved_at, sha256, licence_id, row_count)   # immutable
  silver/   typed, UTC, de-duplicated Parquet, Hive-partitioned:
            ohlcv_1m/venue=binance_spot/symbol=BTCUSDT/year=2026/*.parquet
            funding/, oi_metrics/, fx_ohlcv_1m/venue=dukascopy_bid/...
  gold/     features, labels (rebuildable)
news/       events.parquet (append-only), blobs/ (raw html/xml by hash)
warehouse.duckdb   views over the Parquet, no data inside
```

- **Incremental updaters.** Vision monthly files arrive on the first Monday of the month and daily files the next day [V, README], so: monthly backfill once, then daily Vision or REST for the current month. Check the `.CHECKSUM` for every file. Re-check old files periodically, since Binance has republished corrected files before [V]. Cron or launchd, one job per source, each idempotent.
- **Validation (run on every write):**
  1. Normalise all timestamps to UTC `timestamp[us]`; treat values above 1e14 as microseconds (the 2025-01-01 change), otherwise milliseconds.
  2. Gap check against the expected grid. Crypto: every minute. FX: Sunday 22:00 to Friday 22:00 UTC, but confirm per broker. Log gaps instead of forward-filling silently.
  3. Duplicate bar keys; OHLC sanity (high >= max(open, close), low <= min(open, close), volume >= 0); zero-volume runs; price jumps above N sigma.
  4. DST: store UTC only. HistData is fixed EST, UTC-5 all year [V]. MT5 server time is usually a US-DST-linked offset (often described as UTC+2/+3) [U]: build an offset table per broker and verify against a known event.
  5. Cross-check overlapping sources (Binance vs Coinbase close, Dukascopy vs broker) and alert on drift.
- **Point-in-time news design.** Bitemporal columns on every row: `event_time` (what the source claims) and `knowledge_time` = `first_seen_at` stamped by your collector's own clock (keep NTP in sync). Also `fetched_at`, `url_canonical`, `content_hash`, `source`, `revision_no`, `backfilled` (bool), and a pointer to the raw blob. Append-only: a changed article becomes a new revision row. Features may only use rows with `knowledge_time <= decision_time`. Anything pulled historically (GDELT backfill, API history) gets `knowledge_time = ingest time` and `backfilled = true`, and must not be used as if it were known at the time. Snapshot the weekly calendar daily to catch forecast revisions. Use ALFRED vintages for revised macro series, and store both the as-of date and the publication date for COT (published days after its Tuesday data date).
- **DuckDB memory.** Set `memory_limit` explicitly (about 2 to 3 GB) and a temp directory; the default is a large share of RAM [U].

---

## 4. Free-data pitfalls and how they bias backtests

| Pitfall | What I saw / known | Effect on a backtest | Mitigation |
|---|---|---|---|
| **Survivorship / universe selection** | Vision includes delisted symbols (LUNA, FTT, SRM, LUNC) [V]. `exchangeInfo` shows 137 USD-M perps in `SETTLING` status [V]; today's universe is a biased sample | Picking today's top-20 selects coins that survived and grew; inflates returns | Rebuild the universe monthly from historical quote volume in the klines; include delisted; test with symbols that later died |
| **Exchange-specific price** | Binance BTCUSDT closed near 78.6k at 2026-09 start, Coinbase BTC-USD near 67.2k on 2026-11-14 (different dates, not a spread). USDT is not USD | USDT premium/discount and venue basis leak into signals; fills at other venues differ | Train and execute on the same venue; keep a Coinbase/Kraken USD reference |
| **Wash trading / volume** | Cong, Li, Tang, Yang (Management Science 69(11), 2023) find wash trading averaging over 70% of reported volume on unregulated exchanges, and none on regulated ones [S, abstract via search; I did not read the paper or confirm how each exchange is classified] | Volume, liquidity and "volume breakout" features can be fake; slippage assumptions too optimistic for small caps | Prefer price/return features; cross-check volume against a regulated venue; avoid illiquid symbols |
| **Perps are not spot** | Funding, mark vs last price, liquidations, basis | Using spot bars to trade perps ignores funding and mark-price liquidation | Backtest the instrument you trade, with funding applied |
| **Timestamp units** | Spot files switch from ms to microseconds on 2025-01-01 [V] | Silent off-by-1000 errors, mis-sorted merges | Normalise in the loader, unit-test with one 2024 and one 2025 file |
| **Archive revisions** | Binance republished corrected kline and aggTrade files [V, README] | Results change between downloads | Hash and manifest every file; pin versions |
| **FX has no tape** | Dukascopy, HistData and your MT5 broker disagree on ticks, spreads and sessions | Cost and fill assumptions wrong; stop-hunt wicks differ | Train on a deep feed, validate on your broker's own bars; log live ticks yourself |
| **Time zones** | HistData EST fixed; MT5 server time; Dukascopy time convention [U] | Session features and daily bars misaligned (the "daily close" differs by broker) | UTC everywhere; broker offset table |
| **Weekend and holiday gaps** | FX closed Friday evening to Sunday; crypto 24/7; TradFi perps weekend behaviour not checked | Cross-asset features across closed markets create fake zero-return bars | Mask closed sessions per instrument |
| **Short history for new instruments** | XAUUSDT/XAGUSDT under 1 year [V] | Cannot validate across regimes | Use PAXG, Dukascopy XAU as long-history proxies, then validate on the real contract |
| **Licence drift** | Vision terms added 2026-09-30, changed 2026-10-16 [V, repo commits]; Binance may revise at will (§1.4) | Today's permitted use may not hold later | Keep a licence manifest per dataset; record the terms version at download |
| **LLM contamination** | Master report: Claude models list a June 2026 cutoff | Any LLM replay of earlier news is contaminated | Forward-test on data you record from now on |

---

## 5. M4 16 GB feasibility

### 5a. Hardware facts

- M4 memory bandwidth is **120 GB/s**; M4 Pro 273, M4 Max up to 546 [V, Apple newsroom 2024-10]. Mac mini M4 power: **4 W idle, 65 W max** [V, Apple support 103253].
- Metal's recommended working set on this 16 GB class is **10,922 MB** (two thirds of RAM); `sudo sysctl iogpu.wired_limit_mb=N` raises it (macOS 15+, resets on reboot), a maintainer suggested 14000 for a 16 GB machine but warned context stays limited [V, mlx-lm issue #644, README].
- Measured llama.cpp on **base M4 (10 GPU cores, 120 GB/s)**, Llama 7B: **prompt 221 tok/s, generation 24.1 tok/s at Q4_0; 13.5 tok/s at Q8_0; 7.4 tok/s at F16** [V, llama.cpp discussion 4167]. Effective bandwidth is about 92 GB/s (24.1 tok/s x ~3.8 GB, using the Q4_0 7B file size I remember [U]), about 77% of peak. I use that 92 GB/s as the ceiling for the speed estimates below.

### 5b. RAM budget (16 GB)

Snapshot of this machine today with the Claude app, a browser and Spotify open [V, `vm_stat`, `ps`]: wired 1.5 GB, active 6.2 GB, inactive 5.9 GB, compressor 1.6 GB, memory-pressure tool said 79% free.

| Consumer | Budget (GB) | Note |
|---|---|---|
| macOS kernel + services | 3.0 to 3.5 | wired 1.5 + compressed 1.6 observed |
| Desktop apps (Claude app, browser, music) | 0 to 3 | about 3 GB in the snapshot; near 0 if headless |
| Docker/SearXNG | 1 to 2 | Docker Desktop's default VM size not checked [U]; cap it, or run SearXNG natively |
| DuckDB (explicit cap) | 2 to 3 | |
| Python collectors, orchestrator, risk process | 1 | |
| **Left for models** | **about 8 headless, about 5 with desktop apps** | GPU cap 10.9 GB applies on top |

KV cache: about 144 KB per token for a Qwen3-class 4B/8B (36 layers x 8 KV heads x 128 dim x 2 x 2 bytes) [A, architecture numbers from memory, U]; plan 0.5 to 1.5 GB for 4k to 8k context. Newer architectures differ.

### 5c. Capability table

Sizes are Ollama library file sizes [V, ollama.com tags pages]. Speeds are decode estimates from the verified 92 GB/s effective bandwidth divided by file size [A], unless noted. Third-party "tok/s" pages mix estimates and measurements and some exceed the physical bandwidth ceiling (for example 25 to 35 tok/s claimed for a 9B at about 6.6 GB would need above 160 GB/s), so I do not use them [S].

| Model | Size on disk/RAM | Fits 16 GB? | Decode tok/s (base M4) | Evidence |
|---|---|---|---|---|
| Qwen3.5-4B (Ollama default) | 3.3 to 4.0 GB, 256K ctx | Yes, beside other services | about 25 | Size [V]; speed [A] |
| Qwen3.5-9B (Apache-2.0, multimodal, thinking on by default, IFEval 91.5, BFCL-V4 66.1) | 6.6 to 7.6 GB | Yes, tight with desktop apps open | about 12 to 14 | Card [V]; speed [A] |
| Qwen3-8B | 5.2 GB, 40K ctx | Yes | about 17 | Size [V]; speed [A] |
| Qwen3-14B | 9.3 GB | Only alone and headless; near the 10.9 GB GPU cap before KV | about 10 | Size [V]; speed [A] |
| Gemma 4 12B (QAT 7.2 GB, q4_K_M 8.0 GB, 256K ctx) | 7.2 to 8.0 GB | Yes, alone | about 11 | Size [V]; speed [A] |
| Gemma 4 E4B | 6.1 to 6.6 GB | Yes | not estimated | Size [V] |
| **gpt-oss-20b** (MoE, MXFP4) | 14 GB, 128K ctx | **Not co-resident.** One user report: llama.cpp ran at about 26 tok/s using about 13 GB RAM on a Mac mini M4 16 GB; the MLX build crashed with a Metal out-of-memory error (needs ~11.5 GB vs 10.9 GB cap) | about 26 (llama.cpp, single user report) | Report [V, mlx-lm #644] |
| Qwen3.5-27B / Gemma 4 26B / Qwen3.5-35B | 16 to 22 GB | No | n/a | Size [V] |
| bge-m3 embeddings (MIT) | 568M params, about 1.1 GB fp16 | Yes | batch encode; about 0.3 to 0.6 s per 512-token text on GPU [A, rough: 0.6 TFLOP per text] | Licence [V, HF API]; speed [A] |
| Qwen3-Embedding-0.6B (Apache-2.0) | 596M params, about 1.2 GB fp16 | Yes | same order as bge-m3 | Licence/params [V] |
| FinBERT `ProsusAI/finbert` | 109M, about 0.2 GB fp16 | Yes | hundreds of short sentences/s plausible [U] | **Licence cc-by-nc-sa-4.0: fine for personal use only** [V] |
| CryptoBERT `ElKulako/cryptobert` (MIT, 125M) | about 0.25 GB | Yes | similar [U] | Licence [V]; trained on social posts, so check it against headlines |
| Chronos-2 | 119.5M params, Apache-2.0; MLX port `mlx-chronos2` is a single-maintainer 0.0.1 [S from track 03] | Yes (about 240 MB bf16) | tens of ms per series batch-1 [A: TimesFM's 11 ms on M4 Max scaled by 546/120 bandwidth, about 50 ms] | Params/licence [V]; speed [A] |
| TimesFM 2.5 | 231M params, Apache-2.0, MLX backend `pip install timesfm[mlx]` | Yes (about 0.5 GB bf16) | M4 Max numbers in README are for 3.0 (330M): 11.1 ms batch 1, 666 series/s at batch 32 [V]; base M4 several times slower [A] | README [V]. **TimesFM 3.0 weights are non-commercial and not allowed for "commercial or production use"** [V] |
| TinyTimeMixer (TTM r2) | 0.8M params, Apache-2.0 | Trivial, CPU | n/a | Params/licence [V] |
| LightGBM / XGBoost | CPU only; 5 M rows x 100 float32 features = 2 GB in RAM [A] (binned to bytes it is smaller) | Yes | Published reference: Higgs 10.5 M x 28 features, 500 trees, 255 leaves: 130 s on 16 threads of 2 x E5-2690 v4 (old Xeons) [V, LightGBM docs]. For 3 M x 100 features I expect minutes, not hours [A, not measured on M4] | Reference [V]; M4 timing is [A] |
| Small GRU/conv encoder via PyTorch MPS | Tens of MB | Yes | Small models can be slower on MPS than CPU due to transfer/launch overhead; a June 2026 benchmark discussion reported a 2 to 6x GPU advantage across model sizes; unsupported ops need `PYTORCH_ENABLE_MPS_FALLBACK=1` and fall back to CPU [S] | Benchmark both on your data before committing |

**Prompt-processing and extraction throughput [A].** Prefill is compute-bound, so I scale the verified 221 tok/s (7B) by parameter count: about 370 tok/s for a 4B, about 165 for a 9B. For an article job of 1,000 prompt tokens and 150 output tokens (JSON), thinking off:
- 4B: 1000/370 + 150/25 = 2.7 + 6.0 = 8.7 s, so about **410 articles/hour**.
- 9B: 1000/165 + 150/14 = 6.1 + 10.8 = 16.9 s, so about **210 articles/hour**.
- Qwen3.5 thinks by default; turn it off (`enable_thinking: False` per the card [V]) or throughput collapses.

At 3,000 deduped articles/day, a local 4B needs about 7 hours of full-duty GPU time per day; a 9B about 14 hours. That is why bulk extraction should go to Haiku and local should be a pre-filter.

**MLX vs llama.cpp / Ollama.** One third-party article claims MLX is 15 to 35% faster, but it mixes estimates and measurements and contradicts itself in places [S]. The verified datapoint goes the other way on a 16 GB box: gpt-oss-20b ran under llama.cpp and crashed under MLX [V]. Ollama's library now publishes `-mlx` and `nvfp4` tags (for example `gemma4:12b-mlx`) [V]. `mlx_lm.server` documents OpenAI-style chat but no tool-calling or JSON-schema enforcement [V, SERVER.md]; Ollama documents JSON-schema structured output through `format` [V], though its page does not state the mechanism. **Recommendation: Ollama for LLMs (schema outputs, simple ops), MLX only where the library ships it (TimesFM backend, optional Chronos-2).**

**Structured output and tool calling at this size.** Qwen3.5-9B's card reports BFCL-V4 66.1 and IFEval 91.5 [V]: instruction following is strong, function calling is roughly two-thirds on a hard benchmark. In practice: always validate against a Pydantic schema, retry once, then escalate to Claude. Do not give a 4B to 9B model tool access with side effects.

---

## 6. Recommended local lineup, schedule and Claude split

### 6a. Lineup

| Job | Local | Escalate to Claude when |
|---|---|---|
| Dedupe / clustering | Qwen3-Embedding-0.6B or bge-m3 (both permissive) + cosine/MinHash | Never (cheap, deterministic) |
| Sentiment on headlines | FinBERT (personal licence) as one feature; CryptoBERT for crypto social text | Never; log both so you can compare to later returns |
| Relevance triage ("does this touch my instruments?") | Qwen3.5-4B, thinking off, JSON schema | Low-confidence or schema-fail (retry once, then Haiku) |
| Structured event extraction (who, what, instrument, direction, certainty) | Qwen3.5-9B overnight batch for a few hundred to 1.7 k items | Anything over 8k tokens, conflicting sources, or backlog: **Haiku 5.5 (Batch API for 50% off)** |
| Cross-document synthesis, hypotheses, insight ledger | none | **Sonnet 5.5** daily |
| Judge / QA of local vs cloud extraction, ledger scoring | none | Sonnet 5.5; Opus 5.5 only for hard reviews |
| Forecasts (vol, quantiles) | arch/HAR on CPU; TTM; Chronos-2 / TimesFM 2.5 as features | n/a |
| Profitability model | LightGBM (CPU) | n/a |

Hand-label 300 articles first and compare 4B, 9B, Haiku and Sonnet on them; pick thresholds from that, not from my estimates.

### 6b. What runs when (times in UTC, Colombo = UTC+5:30)

Rule: **only one big memory consumer at a time**, enforced by a lock file in the orchestrator. Set `OLLAMA_KEEP_ALIVE` short (minutes) so the model unloads when idle.

| Window | Jobs | Peak RAM |
|---|---|---|
| 24/7 | Recorders (Binance WebSocket incl. `forceOrder`, funding/OI poll, announcements/RSS poll), DuckDB writer, risk gate + execution process | about 2 GB |
| Every 5 to 15 min | News fetch, embed in micro-batches, FinBERT sentiment | +1.5 GB |
| Hourly :05 | Triage with Qwen3.5-4B on new deduped items (about 125/hour at 3 k/day, roughly 30% duty); feature build in DuckDB; LightGBM and volatility inference (seconds) | +4.5 GB |
| Each bar close | Chronos-2 / TimesFM on a handful of series (hundreds of ms) | +1 GB |
| Daily around 06:00 | Claude synthesis (cloud, no local RAM) | 0 |
| Nightly 18:30 to 23:30 | Submit Haiku batch for the hard/backlog items; Qwen3.5-9B on the rest (about 1 k items); walk-forward LightGBM retrain (minutes per model); validation and gap scans | 7 to 8 GB (LLM or training, not both with DuckDB at its cap) |
| Weekend (FX closed) Sat 00:00 to 06:00 | Full purged CV / Optuna on CPU (8 threads), DuckDB compaction, backups, no LLM loaded | CPU-bound, 4 to 6 GB |

Crypto never closes, so keep the always-on process small and make sure no batch job can starve it. Set the risk process to a higher priority and leave 2 GB of slack for macOS.

### 6c. Thermals, always-on

- This machine is a Mac mini [V]: Apple lists 4 W idle and 65 W max for the M4 mini [V]. That is a sensible always-on box. If you also use it as a desktop, desktop apps eat about 3 GB (section 5b).
- If your trading box turns out to be a MacBook, expect throttling under sustained GPU load and battery wear when plugged in all day [U]; prefer the mini.
- Operational items to set up and test (not verified here): start automatically after power failure, disable sleep, disable automatic macOS restarts for updates, a UPS, and an alert if recorders stop. The master report already flags that a sleeping Mac is the real failure mode.
- Purchase info if you ever need a second box [S]: Apple announced the Mac mini with M6 on 2026-08-25, from **$899** for 16 GB/256 GB (M5 Pro from $1,699); the M4 mini was reported as no longer sold new from 2026-09-22; used M4 16/256 units were seen at about $650 to $730. Apple's own page fetched today lists M6 and M5 Pro only and no prices [V]. I did not verify these figures on Apple's store.

### 6d. Claude monthly cost estimate

Prices [V, platform.claude.com pricing page, fetched today]: **Haiku 5.5 $0.10 in / $0.50 out per MTok** (prompts up to 100k; $0.50/$2.50 above), **Sonnet 5.5 $2 / $10**, **Opus 5.5 $4 / $20**, Fable 5.2 $8 / $40. Batch API is 50% off both directions. Cache reads on Sonnet 5.5 and Opus 5.5 are 0.05x input. Haiku 4.5 is still listed at $1 / $5.

Assumptions are mine; change them to match your volume.

| Line | Assumption | Standard price |
|---|---|---|
| A. Haiku 5.5 bulk extraction | 3,000 articles/day x 30 = 90,000; 1,000 in / 150 out each. In: 90 M x $0.10 = $9.00. Out: 13.5 M x $0.50 = $6.75 | **$15.75** ($7.88 on Batch) |
| B. Sonnet 5.5 synthesis | 4 runs/day x 30 = 120; 60k in / 3k out. In: 7.2 M x $2 = $14.40. Out: 0.36 M x $10 = $3.60 | **$18.00** (less with caching of the static prefix) |
| C. Sonnet 5.5 judge/QA | 80 runs/month; 100k in / 5k out. In: 8 M x $2 = $16. Out: 0.4 M x $10 = $4 | **$20.00** |
| D. Opus 5.5 occasional deep review | 20 runs; 150k in / 8k out. In: 3 M x $4 = $12. Out: 0.16 M x $20 = $3.20 | **$15.20** |
| **Central total** | | **about $69/month** |
| Lean | A on Batch ($7.9), B at 2 runs/day ($9), C halved ($10), no D | **about $27** |
| Heavy | 10k articles/day (A = $52.5), B at 12 runs/day ($54), C ($40), D doubled ($30) | **about $175** |

For scale: 10,000 articles x (1,000 in + 150 out) on Haiku 5.5 = 10 M x $0.10 + 1.5 M x $0.50 = **$1.75** [A]. The track 01 figure of about $3.50/day for the same job reflected older Haiku pricing. I have not tested whether Haiku 5.5 extraction quality is good enough; the 300-article hand-labelled set decides that. Claude Code/API use for development is not included.

---

## 7. What NOT to attempt on this machine

- **Co-resident 14B+ models or gpt-oss-20b** next to DuckDB, a crawler and a browser. Under the default GPU cap they crash or swap [V for gpt-oss-20b under MLX]. If you must, run it alone, headless, under llama.cpp.
- **Raising `iogpu.wired_limit_mb` to chase bigger models.** It starves macOS and the always-on processes; it also resets on reboot.
- **Fine-tuning LLMs.** MLX supports LoRA/QLoRA and gives memory tips (batch size 1 to 2, fewer layers, gradient checkpointing) [V], but on 16 GB with a bandwidth of 120 GB/s it is slow, constrains context, and a 4B to 9B model fine-tuned on a few thousand labelled headlines will not beat a small encoder or a GBM on the features that matter. Fine-tune small encoders (FinBERT-size) if anything.
- **Bulk crypto trade history** (about 144 GB for aggTrades) or 5-year FX ticks (about 19 GB) on a 47 GiB disk. Record forward L1/trade summaries yourself instead.
- **Training deep nets on MPS without benchmarking CPU first**; unsupported ops silently fall back.
- **TimesFM 3.0 for a system that trades real money** (non-commercial licence).
- **Using Vision-trained models live without resolving §4.2** (section 0, point 2).
- **LLM backtests over pre-July-2026 news** (training-data contamination, per the master report).
- **Scraping around bot challenges** (Stooq, LBMA, Bluesky, StockTwits, CryptoPanic here); you would be circumventing the sites' controls. Use the sources that answered.

---

## 8. Open questions

1. **Binance Vision §4.2.** Does "live proprietary trading execution" cover a personal bot that uses models trained on the archive? Safer path: train on REST data; consider asking Binance via their GitHub issues. Also unread: the Binance API terms on market-data use.
2. **Is the inspected Mac mini M4 16 GB / 47 GiB-free machine the trading box?** If yes, plan external storage and keep the lake under about 15 GB.
3. **Which broker for MT5?** Needed to measure its real history depth, time offset and spreads. Does the broker's MT5 run well under Wine on macOS, or do you need a Windows VPS? (Execution track.)
4. **Dukascopy terms.** No licence text found. Is a single manual personal export acceptable? Their WAF suggests automation is policed.
5. **CryptoPanic, GDELT, alternative.me, Forex Factory feed terms** on storage and on feeding text to an LLM: not confirmed.
6. **Are Binance TradFi perps (XAUUSDT, XAGUSDT) available and permitted for a Sri Lankan account**, and what are their separate terms and weekend behaviour? (Regulation and execution tracks.)
7. **Local extraction quality.** Qwen3.5-4B/9B vs Haiku 5.5 on your hand-labelled set: unknown until measured.
8. **Measured M4 numbers I did not take:** LightGBM training time, embedding throughput and FinBERT throughput on this machine. A one-hour benchmark script would replace my [A] and [U] numbers.
9. **FRED keyless CSV** failed from this machine for an unknown reason; use an API key and re-test.

---

## Sources (fetched or probed 2026-11-14 unless noted)

- Binance Vision site and README: https://data.binance.vision/ ; https://github.com/binance/binance-public-data ; terms https://raw.githubusercontent.com/binance/binance-public-data/master/TERMS_AND_CONDITIONS.md ; commit history https://github.com/binance/binance-public-data/commits/master/TERMS_AND_CONDITIONS.md
- Vision bucket listing and HEAD requests: https://s3-ap-northeast-1.amazonaws.com/data.binance.vision ; sample files `.../futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-10-01.zip`, `.../spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2026-09.zip`
- Binance API: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints ; https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics ; https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History ; liquidation stream docs via search: https://developers.binance.com/docs/derivatives/coin-margined-futures/websocket-market-streams/Liquidation-Order-Streams ; `https://fapi.binance.com/fapi/v1/exchangeInfo` ; `https://api.binance.com/api/v3/exchangeInfo`
- CoinGecko pricing: https://www.coingecko.com/en/api/pricing.md ; CryptoPanic: https://cryptopanic.com/developers/api/about (search summary only)
- Coinbase https://api.exchange.coinbase.com ; Kraken https://api.kraken.com ; Deribit https://www.deribit.com/api/v2 ; DefiLlama https://api.llama.fi ; Fear and Greed https://api.alternative.me/fng/
- Dukascopy: https://www.dukascopy.com/swiss/english/marketwatch/historical/ ; https://www.dukascopy.com/swiss/english/legal-pages/important-disclaimer/ ; https://github.com/Leo4815162342/dukascopy-node
- HistData: https://www.histdata.com/f-a-q/ ; https://www.histdata.com/download-free-forex-data/
- MT5 Python docs: https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrom_py ; forum https://www.mql5.com/en/forum/490426 ; Windows-only report via search of https://www.mql5.com/en/forum/425741 and https://pypi.org/project/siliconmetatrader5/
- CFTC: https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm ; https://publicreporting.cftc.gov ; SEC: https://www.sec.gov/os/accessing-edgar-data ; ECB: https://data-api.ecb.europa.eu ; Fed: https://www.federalreserve.gov/feeds/press_all.xml , https://www.federalreserve.gov/json/calendar.json ; GDELT https://gdeltproject.org/data.html ; calendar JSON https://nfs.faireconomy.media/ff_calendar_thisweek.json
- Wash trading: https://econpapers.repec.org/RePEc:inm:ormnsc:v:69:y:2023:i:11:p:6427-6454 (via search; paper not read)
- M4 facts: https://www.apple.com/newsroom/2024/10/apple-introduces-m4-pro-and-m4-max/ ; https://support.apple.com/en-us/103253 ; benchmark https://github.com/ggml-org/llama.cpp/discussions/4167 ; MLX issue https://github.com/ml-explore/mlx-lm/issues/644 ; https://github.com/ml-explore/mlx-lm ; LoRA doc https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md ; server doc https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md
- Models: https://ollama.com/library ; tags pages for qwen3.5, qwen3, gemma4, gpt-oss ; https://huggingface.co/Qwen/Qwen3.5-9B ; HF API for ProsusAI/finbert, ElKulako/cryptobert, BAAI/bge-m3, Qwen/Qwen3-Embedding-0.6B, amazon/chronos-2, google/timesfm-2.5-200m-pytorch, ibm-granite/granite-timeseries-ttm-r2 ; https://github.com/google-research/timesfm ; https://lightgbm.readthedocs.io/en/latest/Experiments.html ; https://docs.ollama.com/capabilities/structured-outputs
- Third-party, low confidence (not relied on for numbers): https://willitrunai.com/blog/mlx-vs-ollama-apple-silicon-benchmarks ; https://willitrunai.com/macs/m4-16gb ; https://llmcheck.net/blog/best-local-llm-16gb-mac/
- Claude pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Mac mini price snippets (secondary): https://www.igeeksblog.com/mac-mini-m6-m5-pro-price-specs-release-date/ ; https://www.implicator.ai/apples-first-2nm-chip-lands-in-the-899-mac-mini-its-cheapest-desktop/
- Local probes on this machine: `system_profiler SPHardwareDataType`, `vm_stat`, `df -h /`, `ps` (Mac mini Mac16,10, Apple M4, 16 GB).
