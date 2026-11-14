# Project Get-Rich: Master Research Report

Date: 2026-11-14. Synthesis of seven parallel research tracks (files `01`–`07` in this folder). This is engineering research, not investment, legal or tax advice.

**How much to trust this.** I re-checked star counts, licences and last-push dates for 12 key repos against the GitHub API; all matched what the agents reported. I did NOT re-verify papers, prices, regulatory dates or the community claims. Each track report tags its own claims as seen / snippet / unverified; read those tags before relying on a specific number. Reddit, X, Instagram and TikTok were not reachable by any agent or by me (the built-in browser blocks reddit.com and Claude in Chrome was not connected), so no first-hand social-media evidence is included.

Assumptions not yet confirmed by you: Apple Silicon Mac (RAM unknown), local-first with Claude as the only cloud LLM, personal (not commercial) use, country unknown.

---

## 1. Bottom line

1. **Nobody has shown a durable, cost-adjusted edge from LLM trading agents.** StockBench, FinSABER, the "Alpha Illusion" paper, live experiments like Alpha Arena and the DXRG record all point the same way (tracks 01, 07). The agent layer is worth building as an *information-extraction and hypothesis layer feeding a classical model*, not as a decision-maker.
2. **Zero-shot forecasting models don't beat a random walk on returns** (track 03). Volatility, cross-sectional ranks, trend and carry are where the evidence is. Forecast volatility and quantiles; treat price direction as unproven.
3. **The honest test is forward testing on data you record yourself.** All current Claude models list a June 2026 training cutoff, so any Claude-based historical replay before about July 2026 is contaminated (track 01). The clock on clean evidence only starts when you start recording. **Start the news store and insight ledger first.**
4. **Your idea has a real gap in the open-source landscape.** No project combines leak-safe evaluation, an insight-to-outcome labeling loop, a trained profitability index, an LLM-proof risk layer and cost-aware promotion gates (track 07). That gap is the opportunity and also the risk: it is hard because it is unsolved.
5. **Retail base rates are brutal:** 55–80% of retail CFD accounts lose money per broker disclosures fetched today (IG UK 70%, CMC 69%, Pepperstone 80%, eToro 55%); a Brazil study found 97% of persistent day traders lost. Latency-sensitive news trading and FX/gold CFD scalping are where small players get eaten (track 07). Slow, diversified, low-turnover systematic approaches are the plausible niche.
6. **Treat real money as the last gate, not the goal of the first version.** The plan below puts forward evidence, paper trading and micro-live ahead of any scale-up.

---

## 2. Decisions by layer

| Layer | Recommendation | Local? | Why (key evidence) | Main risk |
|---|---|---|---|---|
| **Agents / research** | Thin custom pipeline: collectors → append-only timestamped store → local extraction → Claude synthesis → **insight ledger** scored later against realized returns. Use TradingAgents (Apache-2.0, 122k stars) as a *reference*, not a dependency. | Mostly. Local: RSS/EDGAR/Fed/ECB/CFTC/GDELT collectors, SearXNG, Crawl4AI, bge-m3 embeddings, FinBERT, small local Qwen-class model. Cloud: Claude only, for synthesis and judging. | Track 01. Free sources cover most metals/FX macro needs. Haiku bulk extraction is about $3.50/day for 10k articles by the agent's arithmetic. | Parametric leakage; prompt injection from web text (one fake headline crashed simulated markets in every run of a 2026 survey); FinBERT is non-commercial licence (cc-by-nc-sa-4.0). |
| **Market data** | Parquet + DuckDB. Dukascopy tick/bar export for FX and metals (free), Databento for COMEX gold futures if wanted ($125 free credits, pay-per-GB), EODHD or Tiingo for equities ($20–$100/mo), FRED/COT/EDGAR for macro (free). | Yes, bulk-download model. | Track 02. FX has no central tape, so train on one deep feed and validate on the execution broker's own data. | Data licences: none of the licences seen explicitly allows or forbids ML training on stored data. Dukascopy data licence text not found. yfinance is personal-use only. |
| **Forecasting** | Volatility first (GARCH/HAR via `arch`; TinyTimeMixer as a challenger), then recalibrated quantiles and triple-barrier probabilities. Chronos-2 (MLX port) and TimesFM 2.5 as optional feature generators. | Yes (Apache-2.0 weights; avoid TimesFM 3.0, non-commercial; TimeGPT is cloud-only and excluded). | Track 03: a preregistered study found 0 of 160 cells beat no-change; Kronos has 47.8k stars but weak independent evidence. | Believing foundation-model output is a price predictor. |
| **Own model (profitability index)** | Start with **LightGBM** on hand-built features. Define PI = E[R_net] from a triple-barrier, cost-aware setup, with two heads: calibrated P(R_net>0) and E[R_net]. Small GRU/conv encoder only if it beats the GBM under the same protocol. "Progressive" = scheduled walk-forward retraining with champion/challenger and shadow deployment, plus drift monitors. | Yes (CPU for GBM; MPS/MLX for small encoders; MLflow/DVC/Optuna on SQLite). | Track 04: trees beat deep nets on medium tabular data; FreqAI's own docs call its continual-learning mode naive and overfit-prone. Take/skip threshold p* = (1+c)/(1+b). | Label leakage and backtest overfitting. Meta-labeling evidence is mixed and thin. |
| **Risk / assets** | Deterministic local risk engine. Fixed-fractional base (0.25–0.5% risk per trade as a *starting point to validate*), volatility scaling, calibrated probability-to-size, cost gate, Kelly only as a ceiling. Shrunk covariance with HRP or risk parity; Black-Litterman as the entry point for LLM views, with view uncertainty from measured hit-rate and a TTL. | Yes (Riskfolio-Lib, skfolio; all run locally). | Track 05. Cap net factor exposure (USD, equity beta, real-yield), not just per-symbol size; gold's real-yield link has been unreliable since 2022. | Gaps through stops (SNB 2015, March 2020); Jan 2026 metals crash details are thin. |
| **Backtest → paper → live** | **NautilusTrader + Interactive Brokers (IB Gateway)** on one codebase. Runner-up: LEAN CLI run locally. Research-only: vectorbt, bt. | Yes, on your own always-on machine. | Track 06. IBKR is the only candidate covering stocks, FX and spot gold/silver with a real paper account. | See "Plan-changing facts" below. |

---

## 3. Reference architecture

```
 LOCAL COLLECTORS  ─►  APPEND-ONLY NEWS/DATA STORE (timestamped on arrival)
 RSS, EDGAR, Fed/ECB,        │  Parquet + DuckDB
 COT, GDELT, FRED,           ▼
 SearXNG, Crawl4AI      EXTRACTION (local small LLM, FinBERT, embeddings)
                             │  structured events, entities, dedupe
                             ▼
                        CLAUDE SYNTHESIS (cloud, off critical path)
                             │  falsifiable, timestamped insights
                             ▼
                        INSIGHT LEDGER (immutable) ──► scored vs realized outcomes
                             │
 MARKET DATA ─► FEATURES ─► FORECASTS (vol/quantiles) ─► PROFITABILITY INDEX MODEL
                                                          (LightGBM → small encoder)
                             │  trade intents only (typed), never orders
 ═════════════════ TRUST BOUNDARY: nothing above can place an order ═════════════════
                             ▼
                        RISK GATE (deterministic, hash-pinned limits file,
                        tighten-only for model/LLM input, works offline)
                             │
                        EXECUTION (NautilusTrader) ─► IB Gateway ─► broker
                             │       broker-side stops are the last line of defence
                             ▼
                        MONITORING / KILL SWITCH / RECONCILIATION / ALERTS
```

**One design conflict the tracks left open, and how I'd settle it.** Track 05 says the risk engine should be a separate process holding the broker credentials. Track 06 puts risk inside the Nautilus node. IB Gateway authenticates a session, so anything that can reach its port can trade. Practical resolution: only the execution/risk process can reach the Gateway (localhost-only binding, separate OS user or container network), the risk gate runs as its own process in front of the Nautilus node, and agents/models have no network path to the Gateway at all. Nautilus has no built-in kill switch per track 06, so you build it.

---

## 4. Plan-changing facts

- **IBC, the standard IB Gateway auto-login tool, was archived on 2026-09-01.** IBKR 2FA still needs phone approval, so expect roughly weekly re-authentication; design to fail safe when it lapses.
- **NautilusTrader is mid-transition.** Stable on PyPI is 1.231.0 (2026-08-02); 2.0.0rc9 landed 2026-11-10, and its README says RC wheels are not for real capital. It has no OANDA, Alpaca or MT5 adapter, so IB is the only built-in route for FX and metals.
- **The US pattern-day-trader $25k rule is gone** (FINRA Notice 26-10, effective 2026-06-04; brokers may phase in until 2027-10-20). Behaviour still varies by broker.
- **Paper trading overstates live results** (Alpaca paper fills against the quote with random partial fills; IBKR paper has order-type gaps). Treat paper as a plumbing test and calibrate costs from micro-live fills.
- **US retail generally can't get spot XAU CFDs** (secondary sources; verify with the broker). US routes are COMEX futures (GC, MGC), ETFs and IBKR's US Spot Gold. Your country changes this entirely.
- **Uptime is the real engineering problem.** A sleeping Mac, a macOS update reboot or an unapproved 2FA prompt silently stops trading. Prefer an always-on small box with broker-side protective orders.
- **OpenBB's repo now lives at `openbq-org/OpenBB`** (75k stars). Two agents noted the redirect and couldn't confirm why; verify before depending on it.
- **Kronos is stale** (last push 2026-04-13 despite 47.8k stars); star counts are not quality signals in this space.

---

## 5. Staged roadmap with gates

Gate numbers below are my suggestions for you to tune, not findings from the research.

| Phase | What | Exit gate |
|---|---|---|
| **0. Foundations (start now)** | Data lake (Dukascopy, FRED, COT, EDGAR bulk, chosen equity feed). **Start recording news and insights today** so the forward-evidence clock runs. Decide instruments and horizon. 1-hour MPS-vs-MLX benchmark on your Mac. | Data reproducible; recorder running unattended for a week. |
| **1. Honest evaluation harness** | Cost model, purged/embargoed CV and CPCV, Deflated Sharpe with a trial counter, baselines (no-change, buy-and-hold, Log-HAR, simple trend/carry). | Harness reproduces a known baseline and rejects a shuffled-label model. |
| **2. Profitability index v1** | LightGBM two-head model on triple-barrier labels; label-permutation test; 2× cost stress. | Beats the simple baselines net of 2× costs under CPCV; DSR positive; permutation test fails to reproduce it. |
| **3. Agent layer in shadow mode** | Ledger of timestamped insights, scored against outcomes. Compare local extraction vs Claude on a hand-labeled set. | Insight-derived features add measurable out-of-sample value in forward data, not just historical replay. |
| **4. Risk gate + execution on IB paper** | Nautilus + IB paper; kill switch; chaos tests (API down, duplicate orders, stale data, 2FA lapse). | Survives fault-injection with no unintended orders; reconciliation matches broker state. |
| **5. Extended paper** | Run for several weeks; compare fills to cost model. | Paper behaviour consistent with the calibrated cost model. |
| **6. Micro-live** | Smallest size your broker allows; reconcile; calibrate real costs. Scale only by a written rule you set in advance. | Live results within tolerance of paper after real costs; drawdown limits respected. |

---

## 6. Open questions (these change the plan)

1. **Country and tax residency:** CFD availability, leverage caps, tax treatment.
2. **Mac chip and RAM** (and whether an always-on machine or VPS is available): decides local LLM and model sizes.
3. **Instruments and horizon:** which FX pairs and metals; which gold/silver instrument (spot, futures, ETF); holding period.
4. **Account size** (affects minimum lots, costs, whether futures are practical).
5. **Paid data acceptable under "local-first"?** Or must everything be free and downloadable?
6. **Personal vs commercial use** (affects data and model licences, e.g. FinBERT).
7. **Who approves IBKR 2FA** when you're travelling?

---

## 7. Unfilled gaps (hand-check suggestions)

- **Reddit** (r/algotrading, r/quant, r/LocalLLaMA, r/LLMDevs, r/Forex), **X**, **Instagram**, **TikTok**, Discord and Telegram communities. All unreachable; the agents saw only search snippets. If you want first-hand colour, skim r/algotrading and r/LocalLLaMA for "local LLM trading research" and "LLM trading bot live results" and tell me what you find.
- **Claude model naming:** track 01 lists a "Fable 5.2" model; this session's model list shows Fable 5.1. Check the Anthropic models page before pinning model IDs.
- **Papers cited by the agents** (arXiv 2511.18578, 2606.27100, 2609.19705, 2611.12141, 2605.16895): not independently opened by me.
- **Unverified items flagged in each track:** Alpha Arena final numbers, Finnhub and Alpaca free-tier terms, local-model tool-calling quality, LEAN's local-live seat requirement, several vendor prices.

---

## 8. Report index

| File | Track |
|---|---|
| `01-agentic-research-layer.md` | LLM agent repos, news/search/crawl tools, sentiment, leakage and evidence |
| `02-market-data.md` | Data providers, metals/FX specifics, storage |
| `03-time-series-forecasting.md` | Foundation models, classical libraries, what is predictable |
| `04-own-model-encoder-classifier.md` | Profitability index formalizations, progressive training, roadmap M0–M6 |
| `05-risk-and-portfolio.md` | Sizing, portfolio construction, layered risk-control spec |
| `06-backtest-paper-live-execution.md` | Frameworks, brokers, paper-vs-live gap, go-live gates |
| `07-community-and-reality-check.md` | End-to-end project landscape, live experiments, retail outcomes, scams checklist |
