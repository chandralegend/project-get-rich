# 02 - Market Data & Instruments (stocks, forex, precious metals)

Researcher track: market data & instruments. Date of research: **2026-11-14**. All prices/limits below are "as seen on that date" from the cited page unless marked **[unverified]**. Constraint added mid-task by the user: **local-first** (only Anthropic Claude as cloud LLM; everything else local, Apple Silicon Mac assumed) - see the "Local-first stack" section.

Tool/reachability notes (honest limits of this research):
- Reddit: direct fetch of reddit.com was blocked by the tool; fetches of third-party Reddit mirror sites were denied by the permission classifier (one also TLS-failed), and I did not try to work around that. Reddit content below comes only from web-search result snippets (threads surfaced via mirror URLs), so it is **thin and second-hand**. No thread text was read in full.
- Hacker News, YouTube, X, Instagram: searches returned no usable HN/YouTube/X/Instagram content. Treat community evidence on those platforms as **not reachable**.
- Several vendor pricing pages are JS-rendered and returned partial data (Massive, Finnhub, Twelve Data had internal inconsistencies). Flagged where relevant.

---

## 1. TL;DR

1. **Polygon.io is now Massive (massive.com)**, rebranded effective Oct 30, 2025; old `api.polygon.io` keeps working, new `api.massive.com` is live. Accounts/keys unchanged. ([press-release summary via search](https://rcnamericageorgia.blogspot.com/2025/11/polygonio-is-now-massive.html), [Massive site](https://www.massive.com/system)). Official Python client lives at `massive-com/client-python` (MIT, 1.5k stars, pushed 2026-11-12; GitHub API redirects from `polygon-io/client-python`).
2. **Best free-and-local foundation for FX/metals:** Dukascopy tick/bar export (free, tick-level, forex + commodities + indices, many instruments back to 2000) via `dukascopy-node` (MIT). **Best for stocks on a budget:** Tiingo ($30/mo personal) or EODHD ($19.99-$99.99/mo), plus Alpaca free (IEX) for live/paper. Best for **gold futures**: Databento (pay-per-GB with $125 free credit, or $199/mo Standard).
3. **Macro/alt features are almost entirely free and downloadable**: FRED (real yields DFII10 back to 2003, breakevens, broad dollar index DTWEXBGS back to 2006, VIXCLS back to 1990 - all verified by live CSV fetch today), CFTC COT (since 1986 legacy / 2006 disaggregated, weekly), SEC EDGAR (bulk `companyfacts.zip`, rebuilt nightly), Fed calendar (fetched).
4. **Gold-specific gotcha:** FRED no longer carries the LBMA gold fixing (ICE Benchmark Administration data was removed Jan 31, 2022 - and the `GOLDAMGBD228NLBM` CSV endpoint returned an HTML error page today). Use futures (GC/MGC), GLD NAV history (SSGA publishes xlsx), or Dukascopy XAUUSD for the price series.
5. **US residents:** spot XAU/XAG as CFDs is generally unavailable to US retail (per secondary sources - verify with broker). The compliant US routes are COMEX futures (GC 100oz, MGC 10oz), ETFs (GLD 0.40% gross expense ratio), and IBKR's "US Spot Gold" (USGOLD). Alpaca does **not** appear to offer forex or metals.
6. **Do not build a serious system on yfinance.** It is unofficial, Yahoo's own API is "intended for personal use only" (per the yfinance README), and 429/breakage threads recur. Use it for prototyping and as a second-opinion cross-check only.
7. **Forex has no tape.** Every broker's/feeds' quotes differ (spreads, timestamps, DST/timezone conventions). Train on one neutral deep feed (Dukascopy), then validate on the actual execution broker's own data before real money.
8. **Storage:** DuckDB + Parquet (partitioned by symbol/date) is the right default for a solo local-first builder; add ArcticDB only if you want a versioned DataFrame store (note it is BSL 1.1, not OSI-open); QuestDB/ClickHouse only if live tick ingestion becomes a real need.

---

## 2. Provider comparison table

Legend: Y = yes/covered, N = not found/no, ? = unverified. "Local-bulk" = can you pull history once and keep it on disk (license permitting) vs needing a continuous cloud API.

| Provider | Stocks | FX | Metals | History / intraday | Free tier (seen) | Paid (seen, date) | Real-time / WS | Licensing notes | Local-bulk? |
|---|---|---|---|---|---|---|---|---|---|
| **Massive (ex-Polygon.io)** [pricing](https://massive.com/pricing), [compare page (vendor-written, checked Nov 4 2026)](https://massive.com/compare/massive-vs-finnhub.md) | Y | Y (REST, WS, flat files; BBO tick quotes; UTC) [docs](https://massive.com/docs/forex) | ? (not seen) | Stocks Advanced page says "20+ years" + websockets; forex tick depth not stated | Per vendor compare page: free = EOD, 2 yrs, 5 calls/min per market | Official pricing page (fetched 2026-11-14) showed only **Stocks Advanced $199/mo** + Financials & Ratios $29/mo, "Individual use only". Vendor compare page says $29/$79/$199 per market, unlimited calls; Business plans $999 (Currencies) / $1,999 (Options) / $2,499 (Stocks) per month. Third-party sources agree on $29/$79/$199 ([search summary](https://apicostcalc.com/blog/polygon-massive-rebrand-api-pricing.html)) | Y (WS on Advanced) | Individual use only on self-serve; business pricing separate | Y - flat files exist (per r/algotrading snippet) |
| **Alpaca** [data page](https://alpaca.markets/data) | Y (US) | N (no forex pair trading found; "local currency trading" is FX conversion for stocks) | N found | 7+ yrs; bars, snapshots, corp actions | $0: IEX only, WS limited to 30 symbols, 200 calls/min, 15-min delayed via API | **Algo Trader Plus $99/mo**: all US exchanges, unlimited calls, real-time options (OPRA) | Y (free WS IEX only) | Tied to brokerage account | Partial (bars via API) |
| **Databento** [pricing](https://databento.com/pricing) | Y (US Equities, OPRA) | N | **Y via CME futures (GLBX.MDP3: CME/CBOT/NYMEX/COMEX; since 2010; "from $0.50/GB")**; GC page not retrievable ([catalog](https://databento.com/datasets/GLBX.MDP3/futures/GC)) | Tick/L1/L2/L3; Standard: 16+ yrs L0, 1 yr L1, 1 month L2/L3 | **$125 one-time credits, expire 6 months** | Usage-based historical $/GB; **Standard $199/mo** (live, no license fees); Plus $1,750/mo; Unlimited $4,500/mo (annual contracts) | Y (Standard) | Standard: instant approval personal use; redistribution after 24h per dataset terms | **Yes - best pay-once-download model** (`get_cost` is free to preview) |
| **Twelve Data** [pricing](https://twelvedata.com/pricing) | Y | Y (real-time on free) | "commodities" from Grow tier; metals not named | Not stated on page | Basic $0: 8 credits/min, 800/day, internal non-display use | Grow $79, Pro $229, Ultra $999 (page internally inconsistent with schema data $29/$99/$329 - **confirm**) | WS: 8-credit trial on Basic/Grow; full on Pro+ | Personal vs commercial split | Partial |
| **Tiingo** [pricing](https://www.tiingo.com/about/pricing) | Y (110,518 securities, 30+ yrs price history, incl. ETFs/mutual funds; IEX feed) | Not mentioned | Not mentioned | 30+ yr EOD; fundamentals 5 yrs (free) / 15+ yrs (paid, add-on) | Starter $0: 500 unique symbols/month, 50 req/hr, 1,000/day, 1 GB/mo | **Power $30/mo** ($300/yr): 10,000 req/hr, 100k/day, 40 GB; internal commercial $50/mo or $499/yr | IEX feed listed | "Internal use only"; no display/sharing; redistribution separate | Yes (EOD bulk loop within limits) |
| **Finnhub** [vendor compare, not primary](https://massive.com/compare/massive-vs-finnhub.md) (finnhub.io/pricing page did not render) | Y | Y (separate module/price) | ? | Stock candles are premium (free returns 403) | 60 calls/min, WS 50 symbols, personal use | US market data $49.99/mo (quarterly $129.99; annual $199.99 per vendor page), fundamentals $50-200/mo; All-In-One $3,500/mo | Y | Every self-serve plan personal use; commercial = Enterprise | Limited on free |
| **Alpha Vantage** [premium](https://www.alphavantage.co/premium/) | Y | Y (? - not on page) | ? | n/a on page | **25 requests/day** | $49.99 (75/min), $99.99 (150/min), $149.99 (300/min), $199.99 (600/min), $249.99 (1,200/min); second unlabeled group $499-$2,499 | Realtime/15-min US via entitlement (personal use) | Personal-use entitlement | Weak (25/day free) |
| **EODHD** [pricing](https://eodhd.com/pricing) | Y (30+ yrs EOD) | Y (EOD all plans; intraday FX on Active trader/All-in-one) | **Y - metals/energy/ag commodities on every plan incl. Free** | EOD 30+ yrs; intraday on Active trader+ | Free sandbox: 1 yr EOD, 20 calls/day (+500 bonus), 15-min delayed | Historian $19.99/mo EOD; Active trader $29.99 (EOD + intraday); Equity analyst $59.99 (fundamentals); **All-in-one $99.99**; 100k calls/day; intraday costs 5 calls, fundamentals 10 | Live on paid (non-fundamentals) | Personal vs commercial/B2B plans | Yes (100k calls/day allows bulk) |
| **OANDA v20** | N | Y | Y (XAU_USD etc. - availability depends on entity/country, **unverified**) | Candles ~5,000/request (3rd-party wrappers); history back to ~2005, S5 to monthly (3rd-party directory, **unverified**) | Free with a (demo/live) account | n/a | Y (streaming pricing) | Account terms; v20 is not available for OANDA Global Markets entity (3rd-party note) | Partial (broker-specific data!) |
| **Dukascopy** [export page](https://www.dukascopy.com/swiss/english/marketwatch/historical/) | Y (CFDs/stocks via dukascopy-node list: ~546 US stocks) | Y (290 forex currency instruments per `dukascopy-node` list; EUR/USD earliest 1973-03-01, many from 2000-01-01) | Y (commodities incl. gold/silver per Tickstory; page says "Forex, Commodities and Indices") | Tick-by-tick to monthly, CSV | **Free** | n/a | n/a | No data-license text found on the export page; downstream tools say you are bound by Dukascopy's terms; **check before commercial use** | **Yes - the ideal one-time bulk** |
| **TrueFX** [page](https://www.truefx.com/truefx-historical-downloads/) | N | Y (Integral OCX, "250+ banks, brokers and asset managers", ms tick, top-of-book) | Not confirmed | Not stated on page | Free with registration | n/a | n/a | No terms on page | Yes |
| **IBKR TWS API** [limits](https://interactivebrokers.github.io/tws-api/historical_limitations.html) | Y | Y | Y (see section 3) | Pacing: >60 requests/10 min violates (BID_ASK counts double), max 50 open requests; bars <=30 s older than 6 months unavailable; expired futures >2 yrs after expiry unavailable; delisted securities unavailable | Needs funded account + market-data subscriptions | n/a | Y | Doc says docs are deprecated -> IBKR Campus | Poor for bulk history; fine for execution + recent data |
| **FRED** [terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html) | macro | Daily FX (e.g. DEXUSEU 1999-) | Gold fixing removed 2022 | Daily/weekly/monthly series | Free API key | n/a | n/a | Terms silent on caching; third-party series may be copyrighted; can't clone FRED UX | Yes |
| **Stooq** [bulk page returned empty to fetch; no first-party confirmation] | Y (global daily; free 5/60-min intraday claimed by a video-based source) | Y | Y | Decades daily | Free | n/a | n/a | Third-party reports say API/CSV now needs a CAPTCHA-issued key and has daily hit limit (**unverified**, [summary](https://apis.io/apis/stooq/stooq-q-api/)) | Yes manually |
| **yfinance / Yahoo** [repo](https://github.com/ranaroussi/yfinance) | Y | Y | Y (futures/ETFs) | EOD + limited intraday | Free, unofficial | n/a | delayed | README: Yahoo API "intended for personal use only"; Apache-2.0 library, **not** a data license | Yes, but fragile |
| **Nasdaq Data Link** | ? | ? | ? | n/a | n/a | n/a | n/a | Pages 404/redirect; **not verified** | ? |
| **Norgate Data** | Y (survivorship-bias-free US/AU/CA) | N | futures (Y, ?) | US daily back to ~1990 (third-party) | trial | Pricing sources conflict: $35/mo (NexusFi), $630/yr (QuantConnect forum), ~$270-788/yr (competitor MarketParquet) -> **verify on norgatedata.com**. Windows-oriented software [**unverified for macOS**] | n/a | Personal | Local DB via their updater |
| **OpenBB Platform** [repo](https://github.com/OpenBB-finance/OpenBB) | aggregator | aggregator | aggregator | n/a | Free (Apache-2.0; LICENSE file says all files Apache-2.0) | n/a | n/a | You still need each underlying provider's license | n/a |

Sources for the table beyond those linked inline: yfinance/GitHub repo data fetched via `gh api` on 2026-11-14.

### Key naming/verification notes
- **Polygon -> Massive:** confirmed rename (see TL;DR). Massive's own pricing page is JS-heavy; a direct fetch only exposed Stocks Advanced $199/mo and "Individual use only". I could not retrieve Currencies pricing from Massive itself.
- **Alpaca free tier contradiction:** the page header claims "up to 10,000 API calls/min" while the table says 200/min on free; I trust the table.
- **Twelve Data page** contradicts its own schema data on prices; confirm before purchase.

---

## 3. Metals instrument guide (gold XAU, silver XAG)

| Instrument | What it is | Data implications | Execution implications | Who offers it |
|---|---|---|---|---|
| **Spot XAUUSD / XAGUSD (CFD or OTC)** | Over-the-counter; quotes are broker-specific | No central tape; use broker or neutral feed (Dukascopy) | CFDs generally **not** available to US retail (secondary sources: [daytrading.com](https://www.daytrading.com/us/cfd), MQL5 forum); swap/financing and spreads vary per broker | Outside US: most FX/CFD brokers; IBKR **XAUUSD for non-US residents** (EU site: most customers not resident in US/Canada/Australia/HK/Japan); US: IBKR "US Spot Gold" (USGOLD) for US residents except AZ/MT/NH/RI (per IBKR guide as of 2021 launch coverage - **verify now**) |
| **COMEX futures GC (100 oz)** | Exchange-traded, physically settled (most close/roll before delivery) | Real tape (CME MDP 3.0), contract rolls and continuous-contract construction required; Databento GLBX.MDP3 since 2010 | Margin-based; tick/size known; liquidity concentrated near front months | IBKR (futures), many FCMs |
| **Micro Gold MGC (10 oz)** | 1/10 GC; 10c tick = $1; margin ~1/10 of GC; 10:1 offset vs GC ([CME-derived summary](https://help.metrotrade.com/kb/micro-gold-futures-mgc-contract-specifications)) | Same CME feed, same roll handling | Best sized for small accounts; dollar margins quoted by sources vary ($825 - $2,333) so check CME/clearer current schedule | IBKR and other FCMs |
| **Gold ETFs (GLD, IAU) / silver (SLV)** | Physically backed funds. GLD: 0.40% gross expense ratio, HSBC/JPM custodians, shares outstanding 366.40M, AUM $130.6B, NAV $356.53 on SSGA page seen 2026-11-14 ([SSGA GLD](https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld)) | Equity-style daily/intraday data; **corporate-action-free** but tracks gold with fee drag; SSGA publishes NAV and premium/discount history xlsx; holdings (tonnes) not on the page fetched; IAU/SLV details **not verified** | Trade in any stock broker incl. Alpaca; cash account, fractional, no leverage unless margin | All stock brokers |
| **Physical-backed tokens / bullion** | Not researched in depth | Spot reference only | Storage/spread frictions | **Unverified/out of scope** |

Practical implication for the platform: train/forecast on a long, clean series (Dukascopy XAUUSD ticks -> bars, plus GC futures from Databento for a real-tape cross-check), then execute through whichever instrument the user's residency allows. The signal on spot vs futures differs by basis/roll and session; model each instrument as its own tradable.

---

## 4. Forex specifics

- **No central tape.** FX is OTC; each liquidity provider/broker streams its own quotes ([StrategyQuant on feed differences](https://strategyquant.com/blog/preparing-accurate-data-for-algo-trading-broker-data-feed-differences)). Spreads, tick timestamps and even daily open/close differ.
- **Timezones and DST:** brokers use different server timezones (e.g. UTC+2 with EET DST vs "EST+7" style conventions listed in that article, which warns the info may be outdated). A DST mismatch can shift D1/H4 candles by an hour for a few weeks per year. **Store raw data in UTC; derive broker-aligned bars separately.**
- **Spread/cost modelling:** backtests on mid or Dukascopy bid/ask often don't reflect the live broker's variable spread; MQL5 threads repeatedly cite this as the top source of backtest/live drift ([MQL5 thread 146943](https://www.mql5.com/en/forum/146943/3703284), [thread 409907](https://www.mql5.com/en/forum/409907)). Anecdotal.
- **Silent gaps:** MQL5 users report MT5 history center forward-filling gaps ([MQL5](https://www.mql5.com/en/forum/287982/page2)).
- **Why one-broker backtests mislead:** different LP mix -> different spikes, stop-hunt wicks, rollover spreads. One poster suggests a strategy that only works on one broker's data "is not robust". Advice: develop on a neutral deep feed, check on a second feed, and verify on the target broker's own ticks.
- **Swap/rollover data** is broker-specific and is not provided by the free historical feeds; you must log it from the broker (OANDA/IBKR) or model it from interest-rate differentials (FRED has policy/short-rate series) - **unverified build recommendation**.
- **Session effects:** Asia/London/NY overlaps, Friday close and Sunday open gaps, rollover at ~5pm NY; for gold, COMEX session breaks and London fix windows. Build session features explicitly (the platform's feature layer, not the data layer).

---

## 5. Data-quality pitfalls and tools

| Pitfall | What goes wrong | Mitigation / tool |
|---|---|---|
| **Survivorship bias** | Datasets without delisted names inflate returns; one forum cites 1.5-2%/yr (single unverified figure) | Use a provider with delisted + point-in-time index membership: **Norgate** (most-cited), Sharadar/CRSP (priced for institutions per QuantConnect forum - not verified); IBKR **does not** provide data for securities no longer trading; Yahoo often lacks delisted tickers ([r-bloggers](https://www.r-bloggers.com/2021/08/when-yahoo-finance-doesnt-have-de-listed-tickers-needed/)) |
| **Point-in-time fundamentals** | Restated/late filings leak future info | SEC EDGAR filing-dated facts (`companyfacts`, `submissions`) with `filed` dates; Tiingo/Massive fundamentals are not verified as PIT |
| **Corporate actions** | Unadjusted splits look like -75% crashes (Apple 2020 example, [guide](https://dev.to/tildalice/yfinance-alternatives-2026-7-free-apis-compared-o4g)); "Close" definitions differ across libs (Feb 2025 r/algotrading thread: `Adj Close` disappeared; yfinance Close with `auto_adjust=False` already split-adjusted) | Store **raw + factor tables**, derive adjusted series yourself; reconcile against a second provider; pin yfinance version |
| **Timezone/DST** | Bars misaligned across sources | Store everything in UTC; `exchange_calendars` ([688 stars, Apache-2.0, pushed 2026-11-02](https://github.com/gerrymanoim/exchange_calendars)) / `pandas_market_calendars` ([1,010 stars, MIT, pushed 2026-11-14](https://github.com/rsheftel/pandas_market_calendars)) for session boundaries and early closes |
| **Missing bars** | Forward-fill hides gaps (MT5) | Calendar-aware gap detection; keep a "was-missing" flag; never silently ffill |
| **Look-ahead in resampling** | Resampled bars labelled by open vs close time; using the bar's close before it exists | Label right-closed/right-labelled for features; shift 1 bar before use; unit-test with synthetic data; compute from tick/1m source |
| **Provider-specific bad ticks** | Price off by 10x (EODHD non-US example from an r/algotrading snippet, corrected next day) | Outlier filters + cross-source checks |
| **Rate/size limits breaking pipelines** | 429s (Yahoo), IBKR pacing | Idempotent downloader with checkpointing, backoff, local cache |

**Validation libs:** `pandera` (unionai-oss/pandera, 4.5k stars, MIT, pushed 2026-11-13) for dataframe schemas; Great Expectations (GitHub redirects to `fivetran/great_expectations`, 11.9k stars, Apache-2.0, pushed 2026-11-13 - org move observed via API, verify). Suggestion: pandera schemas on every ingest stage (monotonic UTC index, no negative spreads, OHLC consistency, volume >= 0).

---

## 6. Storage / infra options (solo builder)

| Option | Fit | Pros | Cons | License/activity (seen via GitHub API 2026-11-14) |
|---|---|---|---|---|
| **Parquet files + DuckDB (+ Polars)** | **Default recommendation** | Zero server, SQL over files, fast on Apple Silicon, partition by symbol/date, easy backups, reproducible dataset snapshots | No built-in ingestion service or versioning (use dated snapshots/manifest) | DuckDB MIT 43k stars; Polars MIT 40.3k stars |
| **ArcticDB** | Versioned DataFrame store (python-native), good for research snapshots/time-travel | Serverless; LMDB/local backends; findatapy supports Arctic/ArcticDB | **BSL 1.1** (use grant forbids offering a "Database Service" - fine for personal use but not OSI-open); 2.6k stars; macOS wheel availability not verified | man-group/ArcticDB, pushed 2026-11-14 |
| **TimescaleDB** | If you want Postgres ecosystem + SQL | Compression, continuous aggregates | Server to run; license is Timescale License ("Other"), not plain Apache; overkill for research | 23.9k stars |
| **QuestDB** | High-rate live tick ingestion | Fast ingest, SQL, Apache-2.0 | Separate JVM-ish server; tick volumes of a solo project rarely justify | 17.5k stars; vendor benchmarks claim 4.9x ingest advantage over ClickHouse - treat as marketing |
| **ClickHouse (or chDB embedded)** | Large tick archives, analytics | Cost-effective kdb+ alternative per industry guides | Heavier ops; learning curve | 50.9k stars, Apache-2.0 |

Sources for comparison summary: [timestored](https://www.timestored.com/data/store-market-tick-data), [QuestDB blog (vendor)](https://questdb.com/blog/comparing-influxdb-timescaledb-questdb-time-series-databases), [pkgpulse](https://www.pkgpulse.com/guides/duckdb-vs-clickhouse-vs-questdb-analytical-databases-2026). No tick-specific independent benchmarks found.

Rough sizing intuition (unverified): FX tick history for 20-30 pairs over 10+ years is tens to low hundreds of GB in Parquet; 1-minute bars for all of that are a few GB. Plan for tick-on-demand, bars as the working layer.

---

## 7. Alternative / macro features (where to get them free)

Verified live today (CSV endpoint `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`; latest obs as of 2026-11-14 fetch):

| Feature | Source | Series / location | Range seen | Latest seen |
|---|---|---|---|---|
| 10y real yield (TIPS) - key gold driver | FRED | `DFII10` | 2003-01-02 -> | 2.86 on 2026-11-12 |
| 10y breakeven inflation | FRED | `T10YIE` | 2003-01-02 -> | 2.24 on 2026-11-13 |
| 10y nominal | FRED | `DGS10` | 1962-01-02 -> | 5.10 on 2026-11-12 |
| Broad USD index (use instead of ICE DXY) | FRED (Fed) | `DTWEXBGS` | 2006-01-02 -> | 121.88 on 2026-11-06 |
| EUR/USD daily (Fed H.10) | FRED | `DEXUSEU` | 1999-01-04 -> | 1.1154 on 2026-11-06 |
| VIX | FRED mirror of Cboe | `VIXCLS` (close only) | 1990-01-02 -> | 18.70 on 2026-11-12 |
| Gold fixing | FRED | `GOLDAMGBD228NLBM` | **Not available** (HTML returned; FRED dropped ICE Benchmark data Jan 31, 2022 per [FRED notice](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/)) | - |
| CFTC COT | CFTC | Legacy (since 1986-01-15), Disaggregated and TFF (since 2006-06-13), released Fridays 3:30pm ET for Tuesday data; Public Reporting Environment API, no tokens currently issued ([CFTC](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)) | | |
| Fundamentals / filings | SEC EDGAR | `data.sec.gov` APIs no key; `companyfacts.zip` & `submissions.zip` rebuilt nightly ~3am ET ([SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)). I did not confirm the 10 req/s and User-Agent rules from SEC pages - check Developer FAQ | | |
| Gold ETF NAV / premium-discount | SSGA | xlsx links on GLD page ([SSGA](https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld)) | | |
| FOMC schedule | Federal Reserve | 2026: Jan 27-28, Mar 17-18, Apr 28-29, Jun 16-17, Jul 28-29, Sep 15-16, Oct 27-28, Dec 8-9; 2027 (tentative): Jan 26-27, Mar 16-17, Apr 27-28, Jun 8-9, Jul 27-28, Sep 14-15, Oct 26-27, Nov 16-17 ([Fed](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)) | | |
| ECB/BoE/BoJ calendars | Official sites (not machine-fetched here); aggregator `centralbank.watch` offers ICS but accuracy **unverified**; search results for ECB dates were low-quality | | | |
| DXY (ICE) | Not free officially; use DTWEXBGS or construct from FX majors | | | |
| ETF flows (GLD etc.) | Derive from shares outstanding x NAV history (SSGA xlsx); third-party flow data **not verified** | | | |

FRED note: terms are silent on caching; third-party series may be copyrighted; you cannot build something that replicates FRED UX. Personal local use is clearly fine.

---

## 8. Open-source repos for data ingestion (stats from `gh api` on 2026-11-14)

| Repo | Purpose | Stars | Last push | License |
|---|---|---|---|---|
| [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) (API now resolves to `openbq-org/OpenBB`) | "Open Data Platform": connect providers; Python `obb.equity.price.historical()`, REST, MCP server for agents; `pip install openbb`, Python 3.11-3.14 | 75.4k | 2026-11-14 | Apache-2.0 (LICENSE file: "All files... Apache License 2.0"; GitHub shows "Other") |
| [cuemacro/findatapy](https://github.com/cuemacro/findatapy) | Unified data downloader: Dukascopy, Bloomberg, Quandl, Alpha Vantage, FRED/ALFRED, Yahoo, BoE, Databento (in progress), local CSV/HDF5/Parquet, ArcticDB. "Highly experimental alpha"; release 0.1.42 (2026-03-20) | 2.1k | 2026-07-02 | Apache-2.0 |
| [cuemacro/finmarketpy](https://github.com/cuemacro/finmarketpy) | FX/market backtesting companion | 3.8k | 2026-04-16 | Apache-2.0 |
| [Leo4815162342/dukascopy-node](https://github.com/Leo4815162342/dukascopy-node) | Download Dukascopy tick/bars, ~1,500 instruments; Node >=20; may need headless Chromium for AWS WAF token; 403s possible | 969 | 2026-10-28 | MIT |
| [Lumiwealth/lumibot](https://github.com/Lumiwealth/lumibot) | Python trading framework: backtest, paper, live across 12 brokers (stocks, options, futures, forex, crypto) | 2.2k | 2026-11-14 | GPL-3.0 |
| [microsoft/qlib](https://github.com/microsoft/qlib) | Quant research platform incl. data tooling (equities-focused) | 50.3k | 2026-11-04 | MIT |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | C# engine with local data; Python API | 22.5k | 2026-11-13 | Apache-2.0 |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | Crypto exchange unification (no FX equivalent found) | 44.9k | 2026-11-13 | MIT |
| [alpacahq/alpaca-py](https://github.com/alpacahq/alpaca-py) | Alpaca SDK; old `alpaca-trade-api-python` is **archived** | 1.6k | 2026-11-13 | Apache-2.0 |
| [massive-com/client-python](https://github.com/massive-com/client-python) | Massive (ex-Polygon) client | 1.5k | 2026-11-12 | MIT |
| [databento/databento-python](https://github.com/databento/databento-python) | Databento client | 312 | 2026-11-14 | Apache-2.0 |
| [ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) | Yahoo scraper; latest release v1.8.0 (2026-11-03) | 25.9k | 2026-11-12 | Apache-2.0 |
| [mortada/fredapi](https://github.com/mortada/fredapi) | FRED client | 1.7k | 2026-01-28 | Apache-2.0 |
| [dgunning/edgartools](https://github.com/dgunning/edgartools) | SEC EDGAR Python lib | 2.9k | 2026-11-14 | MIT |
| [sec-edgar/sec-edgar](https://github.com/sec-edgar/sec-edgar) / [jadchaar/sec-edgar-downloader](https://github.com/jadchaar/sec-edgar-downloader) | EDGAR downloaders | 1.4k / 723 | 2025-12-09 / 2026-06-22 | Apache-2.0 / MIT |
| [pydata/pandas-datareader](https://github.com/pydata/pandas-datareader) | Multi-source reader (FRED, etc.) | 3.3k | 2026-07-21 | "Other" (verify) |
| [hootnot/oanda-api-v20](https://github.com/hootnot/oanda-api-v20) | OANDA v20 wrapper (oandapyV20) | 415 | 2023-12-11 | MIT (stale) |
| [oanda/v20-python](https://github.com/oanda/v20-python) | Official OANDA | 267 | 2021-08-01 | - (stale) |
| Backtesters (for context): nautilus_trader 31.5k LGPL-3.0 (2026-11-14); backtrader 23.7k GPL-3.0 (**stale, 2024-08-19**); kernc/backtesting.py 9.2k AGPL-3.0; zipline-reloaded 2.0k Apache-2.0; freqtrade 56.9k GPL-3.0 | | | | |

License flags to watch: GPL (lumibot, backtrader, freqtrade), AGPL (backtesting.py), LGPL (nautilus) - matters only if you ever distribute the platform.

---

## 9. Community findings (limited - see reachability notes)

Evidence is mostly search snippets of r/algotrading threads surfaced through mirror domains (not read in full) plus MQL5/StrategyQuant forums. **Treat as anecdotal.**

- **Databento:** "if it has what you want, in a format you want, it is top notch" but doesn't cover everything (index data a gap in a 2025 thread); usage-based pricing. Thread: ["experience with databento" (Aug 2024)](https://axebps-redlib.hf.space/r/algotrading/comments/1ehslvj/experience_with_databento/lg2lsup/?context=3) (mirror link; snippet only).
- **Polygon/Massive:** users report no problems with live data; commenter notes historical data is bulk-downloadable via flat files. Threads: ["tiingo vs polygon as data source" (Apr 2025)](https://redlib.hbubli.cc/r/algotrading/comments/1ka6yv8/tiingo_vs_polygon_as_data_source/mpkqo5z), ["which API has the most accurate stock data" (Mar 2025)](https://red.127.pp.ua/r/algotrading/comments/1j64t7l/which_api_has_the_most_accurate_stock_data).
- **Alpaca:** an older thread reported close prices not matching Polygon/Yahoo/TradingView; a commenter said Alpaca free data is fine for high-volume ETFs but weak for small caps. Alpaca's own forum has a thread ["Receiving incorrect stock price data"](https://forum.alpaca.markets/t/recieving-incorrect-stock-price-data-from-the-api/4112).
- **EODHD:** one user reported a non-US price off by 10x, fixed next day (snippet).
- **IBKR volume data:** rumored issues, unverified.
- **yfinance:** recurring breakage (Feb 2025 "yfinance down", `Adj Close` column dropped, 429s from cloud IPs/large batches). Threads: [Feb 19 2025](https://r.enesgenc.dev/r/algotrading/comments/1isu4ce/yfinance_down_today), [Feb 22 2025](https://axebps-redlib.hf.space/r/algotrading/comments/1ivlhoz/yahoo_finance_api), GitHub issues [#2128](https://github.com/ranaroussi/yfinance/issues/2128) and [#2480](https://github.com/ranaroussi/yfinance/issues/2480). One test found only 4 of 62,700 adjusted closes differing >0.5% from another provider - accurate often but not guaranteed. yfinance has internal split/100x repair logic.
- **Norgate:** most-cited for survivorship-bias-free data; a r/algotrading thread ["where do you get your data for backtesting from" (Aug 2024)](https://lr.eu.psf.lt/r/algotrading/comments/1et9k3v/where_do_you_get_your_data_for_backtesting_from) recommends it (snippet).
- **Forex data:** MQL5/StrategyQuant: Dukascopy for coarser timeframes/ticks as a neutral reference, but results differ from broker "real tick" data; always verify on target platform ([StrategyQuant](https://strategyquant.com/blog/preparing-accurate-data-for-algo-trading-broker-data-feed-differences), [MQL5 446752](https://www.mql5.com/en/forum/446752), [MQL5 442574](https://mql5.com/en/forum/442574/50709452)).
- **Stooq:** recommended by a video-based source as a free swap-in with decades of daily history; third-party reports of key/CAPTCHA requirement are unconfirmed.
- Not reachable/found: HN threads, YouTube comments, X posts, Instagram.

---

## 10. Local-first stack (new constraint)

Principle: **download once, store in Parquet, query with DuckDB, never depend on a cloud API at decision time.** Cloud LLM = Claude only; all data processing, feature generation and model training are local.

### Cloud-API-dependent vs one-time bulk

| Class | Providers | Notes |
|---|---|---|
| **One-time bulk/offline-friendly** | Dukascopy (tick/bars CSV), FRED (CSV), CFTC COT (annual files/API), SEC EDGAR (`companyfacts.zip`, `submissions.zip`), Databento historical (pay per GB, download once; `get_cost` is free), TrueFX ticks (registration), SSGA GLD xlsx, Stooq (bulk-ish; auth status unverified), Massive flat files (paid; per snippet) | Re-run incremental updates daily/weekly |
| **Continuous API (rate-limited, per-request)** | Alpaca (IEX free; $99/mo all exchanges), Twelve Data, Finnhub, Alpha Vantage (25/day), IBKR (pacing), OANDA, yfinance | Use as incremental updaters/live feeds with local caching; treat the cloud copy as source of truth only for the latest bars |
| **Aggregator** | OpenBB, findatapy | Fine locally; license depends on underlying provider |

### Local storage/ML-training license caveats
- **No provider's page I read explicitly permits or prohibits training an ML model on locally stored data.** What I did see: Massive self-serve = "Individual use only"; Tiingo = "internal use only," no display/sharing; Finnhub free = personal use; Alpha Vantage realtime entitlement = personal use; Twelve Data = internal non-display use on Basic; Databento Standard = personal-use instant approval, redistribution after 24h per dataset; FRED terms silent on caching with third-party series possibly copyrighted; Dukascopy export page = no data license text found; Yahoo = personal use only per yfinance README; SEC EDGAR/CFTC = US government public data. **For a model trained only for your own trading (never distributed), these terms are generally compatible, but this is not legal advice and none of it is confirmed for "model training"** - if you ever sell signals, share weights trained on licensed data, or add a paying user, you need business/redistribution licenses (Massive Business $999-$2,499/mo; Tiingo redistribution; Databento Plus/Unlimited).
- Databento usage-based live was said to be deprecated for other datasets (Mar 31, 2025) and not available for US Equities - read the current pricing before relying on pay-as-you-go live.

### Concrete local layout (suggestion)
```
data/
  raw/<provider>/<dataset>/YYYY/MM/*.parquet   # immutable downloads, UTC
  bronze -> silver -> gold (DuckDB views / Polars jobs)
  reference/ calendars, symbology, corporate_actions, factors
  macro/ FRED, COT, VIX, FOMC dates
  manifests/ dataset hashes + provider/license/date-pulled
```
Ingestion: small Python CLI jobs (`dukascopy-node` via Node, `fredapi`/CSV, `databento`, `alpaca-py`, `edgartools`) run by cron/launchd on the Mac; pandera schemas per stage; exchange_calendars for session logic. Keep a license/provenance manifest per dataset (essential for later commercialization).

---

## 11. Recommended data stack by budget tier

### Free (~$0/mo, fully local-friendly)
- **FX/metals:** Dukascopy tick/bars (XAUUSD, XAGUSD, majors) via `dukascopy-node`; TrueFX ticks as a second FX source (registration; XAU not confirmed).
- **Stocks:** Alpaca free (IEX, 7+ yr bars) + Tiingo Starter (500 symbols/month, 1 GB/mo) + Stooq/yfinance for cross-checks only; SEC EDGAR for PIT fundamentals; **no survivorship-bias-free source on this tier** (accept the bias, limit to current index members' recent history, or use EDGAR filings).
- **Macro:** FRED (DFII10, T10YIE, DGS10, DTWEXBGS, DEXUSEU, VIXCLS), CFTC COT, Fed FOMC dates, SSGA GLD NAV history.
- **Storage:** Parquet + DuckDB. **Paper trading data:** Alpaca IEX websocket (30 symbols).

### ~$100/mo
- Everything above plus: **EODHD All-in-one ($99.99/mo)** *or* **Tiingo Power ($30) + EODHD EOD+intraday ($29.99)**, covering 30+ yrs EOD stocks/FX/metals commodities and intraday; **or** Alpaca Algo Trader Plus ($99/mo) if live SIP data matters; Databento via **pay-per-GB** using the $125 free credits (fetch GC/MGC 1m history once, ~$0.50+/GB, check `get_cost`).
- Optional: Norgate (price unverified, $35/mo to $630/yr range seen) for survivorship-bias-free US EOD - the single best upgrade for stock backtests.

### ~$500/mo
- **Databento Standard $199/mo** (live CME + 16+ yrs L0) + **Massive Stocks Advanced $199/mo** (20+ yrs, WS, individual use) + Norgate/Tiingo + EODHD ~ $500; or Databento + Alpaca Plus + Norgate + Twelve Data Pro ($229).
- FX still best from Dukascopy + the execution broker's own logged ticks (record OANDA/IBKR quotes and spreads yourself for cost modelling; no tier of the vendors above fixes the "broker-specific price" problem).
- Business licensing (Massive Business $999+ or Databento Plus $1,750) is above this tier and only needed if redistributing.

---

## 12. Open questions

1. Massive Currencies/forex plan prices and metals (XAU/XAG) coverage - Massive's own pages did not reveal them.
2. Exact Dukascopy data terms for local ML training/commercial use (no license text found on the export page).
3. Dukascopy XAUUSD/XAGUSD earliest date and bid/ask bars (README listing truncated at 100k chars).
4. Stooq's current access method (API key/CAPTCHA) - unconfirmed first-party.
5. Norgate current price, macOS support, and PIT index-constituent data availability via Python on Apple Silicon.
6. Finnhub, Nasdaq Data Link, TrueFX (XAU, history start): pages did not render/redirect.
7. IBKR: current US Spot Gold eligibility; metals data subscription costs; whether Alpaca adds FX/metals.
8. OANDA US-entity metals availability and exact candle limits (official doc URL 404'd).
9. Whether Massive "individual use only" allows local storage + ML training (read the TOS PDF).
10. Which ETF-flow source (beyond deriving from SSGA shares x NAV) is free for IAU/SLV.
11. Community evidence from HN/YouTube/X/Instagram - not reachable; Reddit only via snippets. A human skim of r/algotrading data threads would add value.
12. ArcticDB BSL terms and Apple Silicon wheels; whether DuckDB alone is sufficient (likely yes).

---

## Appendix: Source URLs (primary)
- Massive: https://massive.com/pricing , https://massive.com/docs/forex , https://massive.com/compare/massive-vs-finnhub.md , https://www.massive.com/system
- Alpaca: https://alpaca.markets/data
- Databento: https://databento.com/pricing , https://databento.com/datasets/GLBX.MDP3/futures/GC
- Twelve Data: https://twelvedata.com/pricing
- Tiingo: https://www.tiingo.com/about/pricing
- Alpha Vantage: https://www.alphavantage.co/premium/
- EODHD: https://eodhd.com/pricing
- Dukascopy: https://www.dukascopy.com/swiss/english/marketwatch/historical/ ; https://github.com/Leo4815162342/dukascopy-node
- TrueFX: https://www.truefx.com/truefx-historical-downloads/
- IBKR: https://interactivebrokers.github.io/tws-api/historical_limitations.html ; https://www.interactivebrokers.com/campus/trading-lessons/trading-spot-gold-and-silver-using-ibkrs-tws/ (403 on direct fetch; facts from search summary)
- FRED: https://fred.stlouisfed.org/docs/api/terms_of_use.html ; CSV endpoints at https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10
- CFTC: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- SEC: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Fed FOMC: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- SSGA GLD: https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld
- yfinance: https://github.com/ranaroussi/yfinance
- StrategyQuant: https://strategyquant.com/blog/preparing-accurate-data-for-algo-trading-broker-data-feed-differences
