# 01 - Agentic Research Layer (LLM agents, news, search, crawl, sentiment, leakage, community)

Researcher: track 1 of 7. Date of research: 2026-11-14.
Scope: the layer that turns news / web / filings into timestamped, scoreable "insights" on stocks, forex and metals. Data vendors for prices, forecasting, the user's own model, risk, execution are other tracks and are only touched where they constrain this layer.

Conventions used in this report
- Star counts, "last push" dates and licenses were read from the GitHub API on 2026-11-14 (`pushed_at` is the last push to any branch, not necessarily the default branch). Anything I could not see directly is marked **unverified**.
- Prices/limits come from the vendor's own page where I could fetch it; where I only found third-party blogs I say so.
- Hardware assumption for the local-first section: **Apple Silicon Mac with unified memory (assumed 32 GB or more; I flag where 16 GB would change the advice).** The user did not state RAM.
- Constraint from coordinator (received mid-task): **local-first; only cloud LLMs allowed are Anthropic Claude.** Folded into every section and summarised in "Local-first stack".

---

## 1. TL;DR

1. **No open-source LLM trading agent has credible, independent, out-of-sample evidence of alpha.** Headline backtests (TradingAgents, FinMem, FinCon) are short, few-ticker, and fall inside the training window of the LLMs used. Independent work finds the edge shrinks or disappears: StockBench (most LLM agents fail to beat buy-and-hold), FinSABER (20 years, 100+ symbols: advantages "deteriorate significantly"), Profit Mirage (reported ~55.7% Sharpe decay for TradingAgents-style systems after the model cutoff), and "The Alpha Illusion" position paper (May 2026). Live experiments (Alpha Arena, the DXRG six-month production record) show no demonstrated edge. See section 5.
2. **Your biggest technical problem is parametric leakage, and it is worse for you than for most.** Every current Claude model (Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5) lists a **training-data cutoff of Jun 2026** ([Anthropic models overview](https://platform.claude.com/docs/en/about-claude/models/overview)). Any historical replay of a Claude-based agent before ~Jul 2026 is contaminated by what the model memorised. Honest evidence therefore comes from **forward (shadow-mode) testing on timestamps you recorded yourself**, starting now. Today is 2026-11-14, so you have ~4.5 months of clean "future" relative to the Claude cutoff, and zero days of your own recorded history. **Start the news store and insight ledger first, before any agent cleverness.**
3. **Do not adopt a trading-agent framework wholesale. Steal ideas, build a thin pipeline.** The recommended shape: local collectors -> append-only timestamped store -> local dedupe/entity-linking/FinBERT/small-LLM extraction -> Claude (Sonnet/Opus/Haiku) for synthesis and judgement -> an **insight ledger** (structured, falsifiable, scored later against realised returns) -> insights become *features* for your own model. TradingAgents is the best reference implementation (Apache-2.0, very active, has been fixing look-ahead bugs release after release, supports Anthropic and Ollama in one config) but it is a stock-ticker decision graph, not a forex/metals macro researcher.
4. **Local-first is feasible for ~90% of the token volume.** RSS/EDGAR/Fed/ECB/CFTC/GDELT collectors, SearXNG, Crawl4AI/Playwright, bge-m3 or Qwen3-Embedding for dedupe, FinBERT (note licence) for sentiment, and a local Qwen-class model via Ollama/MLX/llama.cpp for extraction all run on a Mac. Spend Claude tokens on the minority of hard cases: multi-document synthesis, macro regime narrative, adversarial/hoax checks, LLM-as-judge of local outputs. Haiku 5.5 is $0.10/$0.50 per MTok (Batch API -50%) so even "all extraction on Claude" is ~$3.50/day for 10k articles by my arithmetic (section 7).
5. **Free, high-quality, redistributable-enough sources cover metals/forex macro well:** Fed/ECB RSS, SEC EDGAR (10 req/s, declare User-Agent), CFTC COT (Friday 15:30 ET for Tuesday data), FRED/ALFRED vintages, GDELT (15-minute updates, "100% free and open"). The weak points are **economic-calendar consensus data** (no clean free source), **World Gold Council data** (site terms forbid scraping/redistribution), **X** (pay-per-use) and **Reddit** (approval required, unauthenticated JSON reportedly 403 since May 2026).
6. **Security warning that most repos ignore:** a 2026 SoK reviewed 15 academic LLM trading schemes; 7 code releases enforce no stop-loss/position limit outside the LLM, and a single fabricated headline crashed simulated markets in every run ([arXiv 2609.19705](https://arxiv.org/abs/2609.19705)). Anything that ingests web text is a prompt-injection / hoax surface. Keep order authority and risk limits outside the LLM.

---

## 2. Repo table (open-source agents, frameworks, MCP servers, harnesses)

All numbers fetched 2026-11-14 via GitHub API unless marked.

### 2a. Multi-agent / LLM trading and research systems

| Repo | Stars | Last push | License | Architecture (roles / tools / memory) | News & web handling | Backtest? | Honest limitations |
|---|---|---|---|---|---|---|---|
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 122,489 | 2026-11-04 | Apache-2.0 | LangGraph. Analysts (Fundamentals, Sentiment, News, Technical) run in parallel -> Bull/Bear researcher debate -> Trader -> Risk team debate -> Portfolio Manager. Quick/deep model tiers can use *different providers* (README example: managers on `claude-opus-5-5`). Persistent decision log as memory. Paper: [arXiv 2412.20138](https://arxiv.org/abs/2412.20138). | Yahoo/Alpha Vantage news, StockTwits + Reddit sentiment (optional Typesafe "Jev" screening, a cloud service), FRED macro, Polymarket, SEC EDGAR "as filed". README says company news is read from Yahoo *search* because Yahoo's news feed is down (cf. third-party reports of Yahoo RSS feeds going stale Sep-Oct 2026). | Yes: `backtest.py`, ticker x date grid, scored on next close (v0.5-v0.7). | (1) Release notes list look-ahead fixes in v0.3.1, v0.4.0, v0.5.0, v0.5.2, v0.7.1 (Alpha Vantage, FRED, social sentiment, decision-log memory, model dates reading filings after run date): the tool itself *had* these leaks until recently. (2) Original paper's headline numbers: 3 tickers, ~3-month window in early 2024 (per secondary write-ups; **unverified** against the PDF) - inside GPT-4-class training data. (3) Stock-centric: forex/metals via Yahoo tickers is **unverified**; fundamentals analyst is irrelevant for FX/gold. (4) HN reviewer found prompt-priming and double-weighted sources (section 6). (5) README: runs are non-deterministic. Star count is not evidence of performance; some HN commenters suspect inflated stars (allegation, unverified). |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64,662 | 2026-11-09 | MIT | v2 rewrite: "fund" = allocator over strategy "pods" = analysts (LLM investor-persona agents *and* quant models) -> portfolio construction -> master risk -> broker/ledger ([VISION.md](https://github.com/virattt/ai-hedge-fund/blob/main/VISION.md), much "aspirational" per its own text). TUI with paper trading + backtesting. | Needs Financial Datasets API key (paid; or x402 USDC micro-payments). A third-party hands-on review says investor agents use fundamentals/earnings, **not news** (unverified in code). | Yes, plus paper-trade mode that steps one real session at a time. Reviewer says backtests mask company name/dates and fill at next close ([review](https://davidariasfinance.com/research/ai-hedge-fund-live-run/); I fetched it, not the code). | README: "educational... not intended for real trading". Point-in-time data correctness is still 🚧 in its ROADMAP. Providers: Anthropic, OpenAI, DeepSeek, Google, xAI, Kimi; **Ollama listed as "next"** in v2 roadmap (v1 had it). Reviewer: one run showed most of fund in cash, outcome set by hand-tuned persona weights; "no overfitting check". |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 8,416 | 2026-10-24 | Apache-2.0 | Three generations: V0 AutoGen (educational), V1 OpenAI Agents SDK (web report app), V2 PydanticAI desktop (Tauri app, macOS Apple-Silicon dmg): Lead agent -> Data/Analysis/Modeling/Synthesis/Report agents + Bull/Bear/Judge. Principle: "numbers are code-calculated, narratives LLM-assisted", provenance-tracked. V3 "DeepSeek-Harness" in development. | Equity-research oriented (filings, market data). | Not a trading backtester; it is a research-report generator. | Equity valuation focus (DCF/DDM/LBO/comps); not a news-to-FX/metals signal engine. V1 is OpenAI-SDK-tied. Good *design principle* (deterministic compute vs LLM narration). |
| [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 21,566 | 2026-10-25 | MIT | Open financial LLMs (LoRA on Llama-2/ChatGLM etc.), sentiment models, FinGPT-Forecaster (DOW30). HF: [huggingface.co/FinGPT](https://huggingface.co/FinGPT). | Data-curation pipelines for news scraping (FinNLP repo: 1,496 stars, last push 2024-07-01, stale). | Benchmarks, not a trading backtest. | Models are 2023-vintage (e.g. `fingpt-sentiment_llama2-13b_lora`, last modified 2023-11-06, 0 recent downloads per HF API). Superseded by newer small open LLMs (section 4). Forecaster trained on DOW30 May 2023-May 2024 only. |
| [pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading) | 973 | 2024-08-18 | MIT | Layered memory (short/mid/long) + "character" profile; paper [arXiv 2311.13743](https://arxiv.org/abs/2311.13743). | Hard-wired `text-embedding-ada-002` (OpenAI) + HF TGI models. | Yes (paper's own). | Stale (2+ years). Cloud-embedding dependency. Named in "Alpha Illusion" as a system whose headline Sharpe should not count as deployment evidence. |
| [MingyuJ666/Stockagent](https://github.com/MingyuJ666/Stockagent) | 719 | 2026-06-16 | none listed | Multi-agent *market simulation* (trading/post-trading/special-event phases), [arXiv 2407.18957](https://arxiv.org/abs/2407.18957). | Simulated events, not real news. | Simulation, not a real-data backtest. | OpenAI/Gemini only in README. No licence -> do not reuse code. Simulator, not an alpha tool. |
| [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) | 23,263 | 2026-06-11 | none detected | "Agent-native trading platform": agents register at ai4trade.ai via a SKILL.md, publish signals, copy-trade, $100K paper. | Alpha Vantage with yfinance fallback; "market-intel jobs". | Paper-trading leaderboard; hosted service. | Hosted social/copy-trading platform, not a research stack; sending your agent's signals to a third-party site is the opposite of local-first. Last push 5 months ago. |
| [ValueCell-ai/valuecell](https://github.com/ValueCell-ai/valuecell) | 11,053 | 2026-03-09 | Apache-2.0 | DeepResearch, Strategy (crypto), News Retrieval agents; A2A protocol; data stored locally. | News retrieval agent (scheduled). | Not stated. | README not reviewed in depth. Supports OpenAI-compatible endpoints (so local models) per README. Crypto-leaning. |
| [Y-Research-SBU/QuantHarness](https://github.com/Y-Research-SBU/QuantHarness) | 2,899 | 2026-08-18 | MIT | LangGraph price-only agents: Indicator / Pattern (draws chart) / Trend / Risk. | None (price-driven). | Paper claims; not independently verified. | Not a news agent. |
| [qrak/LLM_trader](https://github.com/qrak/LLM_trader) | 141 | 2026-11-14 | MIT | Paper-trading BTC bot: renders chart + 65 indicators + own closed-trade memory to a multimodal model; deterministic rules check output. Public ledger. | n/a | Live paper ledger since 2026-09-20. | Honest README: +0.05% vs buy-and-hold -9.27% over 52 days, 14 counted trades, "not evidence of an edge", gross of fees, inference cost $7.12, **net after inference -$1.85**. Useful as a template for *publishing* honest forward results. |
| [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) / [microsoft/qlib](https://github.com/microsoft/qlib) | 15,367 / 50,272 | 2026-10-21 / 2026-11-04 | MIT | Qlib = quant research platform; RD-Agent = LLM agent that proposes/implements factors/models on Qlib. | Not news-oriented. | Qlib has a real backtester. | Relevant to track 3/5, mentioned because RD-Agent is the closest "agent that does quant research" to your goal; equity-China/US oriented. |

### 2b. Platforms, MCP servers, harnesses

| Repo | Stars | Last push | License | What it is | Notes |
|---|---|---|---|---|---|
| [OpenBB (OpenBB-finance/OpenBB)](https://github.com/OpenBB-finance/OpenBB) | 75,406 | 2026-11-14 | Apache-2.0 (LICENSE text; GitHub API says NOASSERTION; PyPI `openbb` 5.0.0 says Apache-2.0) | "Open Data Platform": `pip install openbb`, Python + REST + **MCP server** (`pip install openbb-mcp-server`, `openbb-mcp`, tool-discovery mode to avoid token bloat) + Workspace UI. Agents integration in separate [agents-for-openbb](https://github.com/OpenBB-finance/agents-for-openbb) (413 stars). | **Oddity to check:** the GitHub API now answers `OpenBB-finance/OpenBB` with "301 Moved Permanently" to `openbq-org/OpenBB` (same history since 2020-12-20, README still links the old org; recent commit co-authored by a `brightquery.com` address). I could not determine why. Verify the canonical repo/PyPI project before installing. Good *aggregator* of free providers (yfinance, FRED, etc.). |
| [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server) | 1,082 | 2026-11-13 | MIT | Official Alpaca MCP: market data, news, paper/live orders. | Execution lives in another track; for research use read-only. |
| [massive-com/mcp_massive](https://github.com/massive-com/mcp_massive) (= polygon-io/mcp_polygon) | 402 | 2026-11-03 | MIT | Polygon.io (rebranded Massive.com, 2025-10-30) MCP. | Paid data. |
| [alphavantage/alpha_vantage_mcp](https://github.com/alphavantage/alpha_vantage_mcp) | 227 | 2026-10-03 | MIT | Alpha Vantage MCP. | Free key is heavily rate-limited (**unverified** current numbers). |
| [financial-datasets/mcp-server](https://github.com/financial-datasets/mcp-server) | 2,326 | 2025-06-05 | MIT | Financial Datasets MCP. | Stale 17 months. |
| [stefanoamorelli/sec-edgar-mcp](https://github.com/stefanoamorelli/sec-edgar-mcp) | 387 | 2026-11-01 | AGPL-3.0 | SEC EDGAR MCP. | AGPL: fine for private use; matters only if you distribute. |
| [anthropics/financial-services-plugins](https://github.com/anthropics/financial-services-plugins) | 41,282 | 2026-11-12 | Apache-2.0 | Anthropic's reference agents/skills/connectors for equity research, IB, PE (Cowork plugins or Claude Managed Agents). "Market Researcher", "Earnings Reviewer", etc. | Explicitly "do not make investment recommendations, execute transactions". Connectors are mostly to *paid* terminals (partner-built LSEG, S&P Global). Good source of skill/prompt patterns for Claude; not a signal engine. |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 91,978 | 2026-11-12 | NOASSERTION | Reference MCP servers. | Generic. |
| [jackson-cmd/risk-aware-trading-agents](https://github.com/jackson-cmd/risk-aware-trading-agents) | 114 | 2026-11-14 | MIT | Benchmark: frozen point-in-time 2020/2022/2026 markets, news replayed *by the minute published*, fills at next open, look-ahead check on every run; LLM agents over MCP; public leaderboard (rta-bench-1). | Small project; **the design (minute-level news replay + next-open fills) is exactly the right pattern to copy.** Leaderboard figures not reviewed. |
| [HephaestLab/TraderHarness](https://github.com/HephaestLab/TraderHarness) | 43 | 2026-11-12 | Apache-2.0 (per README; API says "other") | Leakage-resistant backtest harness: deterministic entity+date masking, minute-level fills, request-fingerprinted replay, trajectory export. A-share data. | Includes a 21-trading-day, four-model demo (Claude Opus 4.8 +1.45% vs CSI300 -9.12% etc.) that is a *single short window* - treat as a demo, not evidence. |
| [ProjectDXAI/continuous-record-llm-trading-agents](https://github.com/ProjectDXAI/continuous-record-llm-trading-agents) | 51 | 2026-09-10 | CC-BY-4.0 | Data/figures for [arXiv 2609.05663](https://arxiv.org/abs/2609.05663) (see section 5). | Rare production-scale record. |
| [Fincept-Corporation/FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) | 33,790 | 2026-11-13 | AGPL-3.0 | "Modern finance application" (terminal-style). | README not reviewed; **unverified** for agent features. |
| [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 17,068 | 2026-11-03 | MIT | Reinforcement learning (not LLM). | Track 3/5, not this layer. |

### 2c. Generic agent frameworks (finance examples exist but are not finance-specific)

| Repo | Stars | Last push | License | Note |
|---|---|---|---|---|
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 44,940 | 2026-11-14 | MIT | What TradingAgents uses. |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 60,876 | 2026-11-13 | MIT | Role-based crews; many finance tutorials, none I could verify as evidence-bearing. |
| [microsoft/autogen](https://github.com/microsoft/autogen) | 61,810 | 2026-11-12 | CC-BY-4.0 (as reported by API) | FinRobot V0 base. |
| [agno-agi/agno](https://github.com/agno-agi/agno) | 43,184 | 2026-11-14 | Apache-2.0 | Used by ValueCell via A2A. |
| [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) | 8,542 | 2026-11-14 | MIT | The natural orchestration layer for a Claude-first design (TS version: [claude-agent-sdk-typescript](https://github.com/anthropics/claude-agent-sdk-typescript), 1,880 stars). |
| [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | 30,676 | 2026-11-12 | Apache-2.0 | Deep-research agent pattern (search -> crawl -> synthesise), any LLM provider; adaptable for macro briefs. |
| [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research) | 12,677 | 2026-08-10 | MIT | Same pattern, LangGraph. |

**Pattern I would copy rather than a repo I would adopt:** `risk-aware-trading-agents` / `TraderHarness` (leakage-controlled replay), `qrak/LLM_trader` (honest public ledger incl. inference cost), FinRobot ("numbers by code, narrative by LLM"), TradingAgents (structured-output agents, decision log, per-tier provider routing).

---

## 3. News, search and crawl tool comparison

### 3a. News / event feeds

| Source | What it gives | Cost / limits (as seen) | Latency | Licensing for LLM use / redistribution | Fit for this project |
|---|---|---|---|---|---|
| [SEC EDGAR](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) | Filings (8-K, 10-K/Q, Form 4), JSON submissions + XBRL on data.sec.gov, daily feed archives, RSS | Free. Max **10 requests/s**; must send descriptive User-Agent with contact email; "botnets and automated crawlers are not allowed". | Filings accepted 06:00-22:00 ET; current-day indexes updated nightly; RSS feeds near-real-time. | US government data, public. | Core, free, **point-in-time friendly** (acceptance timestamps). Stocks only. |
| Federal Reserve RSS ([feeds page](https://www.federalreserve.gov/feeds/feeds.htm)) | Press releases (all / monetary policy), speeches, testimony, per-governor feeds, e.g. `.../feeds/press_monetary.xml`, `speeches_and_testimony.xml` | Free. | Minutes of publication. | US government. No dedicated FOMC-minutes feed listed on that page. | Core for USD/gold. |
| ECB RSS ([page](https://www.ecb.europa.eu/home/html/rss.en.html)) | Press releases/speeches/interviews, statistical releases, euro FX reference rates (per currency), yield curve | Free. | Minutes. | "Copyright ECB"; reuse terms on separate disclaimer page (not read). | Core for EUR pairs. |
| Bank of Japan | I tried `boj.or.jp/en/rss/index.htm` -> **404**; feed URL **unverified**. | Free (assumed). | | | Find correct feed URL before building. |
| [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) | Legacy / Disaggregated / TFF reports (futures-only and combined), history back to 1986 (Legacy) / 2006 (Disaggregated, TFF); public reporting API (CSV/JSON/XML) | Free; CFTC "isn't currently issuing API tokens". | Released **Fridays 15:30 ET with the preceding Tuesday's data**. | US government. | Gold/silver/FX positioning. **Leakage trap:** key every record by *release time*, not the Tuesday as-of date. |
| FRED / ALFRED | Macro series + vintages (`realtime_start`/`realtime_end`; as-of helpers in clients such as `fredapi`) | Free key. API caps vintage dates at 2000 per realtime window (third-party note). | Daily. | St. Louis Fed terms (not read). | Essential for **point-in-time macro** (revised GDP/CPI/payrolls). Details from third-party clients; verify against FRED docs. |
| [GDELT](https://www.gdeltproject.org/data.html) | Global news-event DB (Events, GKG), DOC API full-text search | "100% free and open"; GDELT 2.0 updates **every 15 minutes**; GKG from Apr 2013. | 15 min | Terms of Use page not read. | Good for geopolitical/gold-relevant event flow and for *historical* backfill; noisy, not finance-curated. |
| [Marketaux](https://www.marketaux.com/pricing) | Global finance news with entities (200k+ entities, 5,000+ sources, 30+ languages) | Free: 100 req/day, **3 articles/request**. Basic $29/mo (2,500 req/day, 20 art/req); Standard $49 (10k req/day, 50 art); Pro $99 (25k req/day, 100 art). | Not stated. | Terms not read; sentiment inclusion/commercial limits **unverified**. | Cheap ticker-tagged supplement. Free tier too thin. |
| [NewsAPI](https://newsapi.org/pricing) | General news search | Developer free: 100 req/day, **24-hour delay**, 1-month search, **not allowed in staging/production incl. internal use**. Business $449/mo (250k req/mo, real-time, 5 years). | 24 h on free | Dev tier forbidden for production. | **Avoid**: delay + licence + price make it a poor fit. |
| Finnhub | Company news, market news, news sentiment, economic calendar, forex/commodity | Free tier ~60 calls/min (third-party; **vendor page was JS-only, not verified**); premium prices conflict across third-party sources ($50-$500+/mo). | REST polling free; WebSocket news is premium (secondary). | **Unverified.** | Probably the best free *ticker-tagged company news* with history; verify terms before relying on it for LLM use. |
| Alpaca News (Benzinga-sourced) | Real-time + historical news **back to 2015**, WebSocket stream (600-900 items/day per docs) | Free plan details only from 2022 beta (200 calls/min free) - **verify current** | Real-time | All data from Benzinga; Alpaca EULA applies (not read). | Good *historical* headline set for stock news with timestamps; only useful if your Alpaca account is free to open. Check whether historical items carry original publish time vs. edit time. |
| Benzinga (direct) | Newsfeed API/WebSocket | No official price list found. Third-party: Pro ~$197-$457/mo (aggregator, **unverified**). May 2026 press release about "AI-ready" APIs for LLM/RAG. | Real-time | **Get written terms for LLM/RAG/redistribution.** | Defer. |
| Polygon -> [Massive](https://massive.com) | News endpoint, bundled with market-data plans | Rebranded 2025-10-30; free-tier/news inclusion claims conflict across sources; **unverified**. | | | Defer to data-providers track. |
| [Tiingo News](https://api.tiingo.com/products/news-api) | Curated news, stocks/FX/crypto | Power ~$30/mo (3-month news history, **personal use only**); Commercial ~$50/mo internal commercial; **no redistribution** on either (via search summary of Tiingo docs). | Real-time | Redistribution needs separate licence. | OK for personal use; short history limits backtests. |
| Yahoo Finance RSS / yfinance | Headlines per symbol | Free, **unofficial**; third-party reports say general Yahoo news RSS stopped updating (404 since 2026-10-06 per one source); per-symbol feeds still worked on 2026-09-28. TradingAgents README independently says Yahoo's news feed is down. | | ToS prohibit scraping (general knowledge; not verified here). | Fragile; do not make it a dependency. |
| World Gold Council / Goldhub | Gold demand trends, central-bank reserves, ETF data | Free downloads exist (daily data back to 2003 per one listing) but the site terms bar "scraping, distributing... derivative works"; LBMA price is licensed from ICE Benchmark Administration; attribution to WGC/Metals Focus required. | Quarterly/monthly | **Restrictive.** | Use manually for context/labels; do not crawl or feed wholesale into a redistributable product. For ETF holdings and price, use other sources (data track). |
| Economic calendar | Release schedule + consensus/actual | Free "Fair Economy / Forex Factory" JSON feed reportedly carries forecast/previous but **not "actual"**; Forex Factory terms reportedly forbid redistribution (both secondary, **unverified**). Trading Economics ~$89/mo (secondary). | | | **Gap.** Build your own calendar from official schedules (BLS/BEA/central banks) and record "actual" yourself at release. Consensus forecasts have no clean free source. |
| X / Reddit / StockTwits / Telegram | Social sentiment | See 3c. | | | Treat as optional, low-trust. |

### 3b. Web search APIs for agents

| Service | Price (vendor page) | Notes for this project |
|---|---|---|
| [Brave Search API](https://brave.com/search/api/) | Search $5/1k requests; Answers $4/1k + $5/M tokens. $5 free credit/month per plan. 50 QPS (Search). `/res/v1/llm/context` endpoint for grounding. | **Storing results or using them to train models requires a custom plan** (FAQ). Independent index. The "Answers" plan uses an LLM -> conflicts with local-first/Claude-only rule; use plain Search. |
| [Exa](https://exa.ai/pricing) | Search $4/1k (lite/instant), $7/1k (auto/fast), deep $12-15/1k; contents $1/1k pages per content type; $10 free credit/month. | Semantic search; good for "find analyst commentary like X". Deep/"reasoning" modes call an LLM server-side (other vendor's cloud LLM) -> avoid under constraint. |
| [Tavily](https://tavily.com/pricing) | Free 1,000 credits/mo; PAYG $0.008/credit; $30/mo for 4,000 credits. Per-endpoint credit costs not on pricing page. | Agent-oriented defaults; credit-based; its optional "answer" feature is an LLM. |
| [Serper](https://serper.dev) | 2,500 free queries, no card. Price/1k and rate limit not captured (page truncated). | Google SERP scraper API; ToS grey area (general knowledge). |
| [Perplexity](https://docs.perplexity.ai/guides/pricing) | Search API $5/1k requests ($1/1k "fast"). Sonar (LLM) models priced separately (page not captured). | **Sonar = another cloud LLM -> disallowed by the local-first rule.** Raw Search API is a search index, not an LLM, but still SaaS. |
| **Claude API web search tool** | **$10 per 1,000 searches** plus token costs ([pricing](https://platform.claude.com/docs/en/about-claude/pricing)); results count as input tokens. | Allowed under the constraint. Opaque index, not point-in-time, cannot be replayed: fine for *live* research, useless as a backtest input. |
| [SearXNG](https://github.com/searxng/searxng) (self-host) | Free, AGPL-3.0, 39,536 stars, pushed 2026-11-13. MCP wrapper: [ihor-sokoliuk/mcp-searxng](https://github.com/ihor-sokoliuk/mcp-searxng) (1,362 stars, MIT). | **Local replacement for all paid search APIs.** It scrapes upstream engines, so expect captchas/rate-limits and upstream ToS exposure; fine for low-volume personal research. |

### 3c. Crawlers / readers and the social sources

| Tool | Facts | Pros / cons for finance |
|---|---|---|
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | 87,333 stars, Apache-2.0, pushed 2026-11-13. Local, LLM-friendly markdown output. | **Default local crawler.** JS rendering via Playwright. No built-in anti-bot guarantee. |
| [Playwright](https://github.com/microsoft/playwright) | 100,130 stars, Apache-2.0. | Needed for JS-heavy pages; slower; easy to get blocked by Cloudflare-protected finance sites. |
| [Scrapy](https://github.com/scrapy/scrapy) | 65,381 stars, BSD-3. | Best for large scheduled RSS/HTML polling with politeness/throttle; no JS. |
| [Firecrawl](https://github.com/firecrawl/firecrawl) | 201,638 stars, AGPL-3.0. Cloud: Free 1,000 credits; Hobby $19/mo (5k credits); Standard $99/mo (100k) ([pricing](https://www.firecrawl.dev/pricing)). | Self-hostable (AGPL); cloud tier is SaaS. Local alternative = Crawl4AI. MCP server: [firecrawl-mcp-server](https://github.com/firecrawl/firecrawl-mcp-server) (7,814 stars, MIT). |
| [Jina Reader](https://github.com/jina-ai/reader) | 12,256 stars, Apache-2.0, last push 2026-05-22 (stale). `r.jina.ai` is a hosted service. | Convenience only; not a local dependency. |
| [browser-use](https://github.com/browser-use/browser-use) | 120,971 stars, MIT. LLM-driven browsing. | Slow/expensive/injection-prone for a data pipeline; use deterministic crawlers for ingestion, LLM-browsing only for ad-hoc research. |

**Anti-bot / ToS reality (finance-specific).** Bloomberg, Reuters, WSJ, Seeking Alpha, Yahoo, TradingView and most calendar sites prohibit scraping in their ToS (general knowledge; I did not fetch each ToS). Paywalled terminals will block automated traffic. Prefer: official RSS/APIs (Fed, ECB, SEC, CFTC, GDELT), licensed news APIs, and crawl only open pages at low rate with a declared User-Agent and robots.txt compliance. Store *your own* observation timestamp for every fetch.

**Social sources (all third-party-sourced summaries unless noted):**
- **Reddit:** third-party guides say API access now requires prior approval under Reddit's Responsible Builder Policy, non-commercial approved apps get 100 queries/min free, commercial use needs a contract, and unauthenticated `.json` endpoints began returning 403 in May 2026; deadlines quoted conflict across sources. I could not fetch Reddit myself (section 6). Treat as **unverified**; check Reddit's own policy pages.
- **X:** per several third-party blogs, pay-per-use became default pricing on 2026-02-06, the free tier closed to new developers, reads cost about $0.005 per post (sources disagree), monthly caps of 2-3M reads. Verify in the X developer console.
- **StockTwits:** per-symbol stream endpoints exist (`api.stocktwits.com/api/2/streams/symbol/{SYM}.json` seen in a scraper listing); developer registration status and rate limits **unverified**.
- **Telegram:** public channels can be read with user-account libraries (e.g. Telethon); ToS/automation limits and signal-channel scam density make this low-value. No source verified.
- All social text is adversarial (pump groups, bots, injection). TradingAgents' own sentiment analyst had a trivially gameable design according to an HN code review (section 6).

---

## 4. Sentiment / NLP

**Findings**
- **FinBERT remains a fast, local, free baseline** but is in-domain trained on Financial PhraseBank: [ProsusAI/finbert](https://huggingface.co/ProsusAI/finbert) (3.2M downloads, last modified 2026-10-12). **Licence flag:** the HF model card reports `cc-by-nc-sa-4.0` (non-commercial) while the GitHub repo reports Apache-2.0; fine for personal research, a problem if this ever becomes a product. `yiyanghkust/finbert-tone` (HF, 501k downloads, last modified 2022-10-17) is the older alternative.
- **LLMs vs FinBERT.** One 2026 paper ([arXiv 2606.12210](https://arxiv.org/pdf/2606.12210)) reports FinBERT ~0.96 macro-F1 on the all-agree PhraseBank subset vs ~0.91 for zero-shot Llama-3.1-8B/Mistral-7B (its own table also lists FinGPT as top; I did not reconcile). A 2025 study ([arXiv 2506.04574](https://arxiv.org/html/2506.04574v1)) finds FinBERT-Tone generalises poorly on harder examples vs zero-shot GPT-4o/4.1 and fails on compositional phrasing like "smaller loss". A Dec 2025 paper ([arXiv 2512.00946](https://arxiv.org/html/2512.00946v1)) finds fine-tuned small open LLMs (Qwen3-8B, Llama3-8B) best in most settings even with 5% of training data. Caveat for all: PhraseBank is **sentence-level sentiment, not tradable signal**; a model that matches human labels can still carry zero alpha.
- **Small fine-tuned finance sentiment models exist** (all author-benchmarked, **unverified independently**): [NOSIBLE/financial-sentiment-v1.2-base](https://huggingface.co/NOSIBLE/financial-sentiment-v1.2-base) (Qwen3-0.6B based, Apache-2.0, 3,353 downloads), `Ayansk11/qwen3-4b-financial-sentiment-grpo`, `AnkitAI/FinSense-ModernBERT-Financial-News-Sentiment`. I found **no MLX-converted finance-sentiment model**; running via llama.cpp/Ollama or `transformers` on MPS is the practical route.
- **A third path (my recommendation, not a verified benchmark):** do not rely on a generic "bullish/bearish" score at all. Use an LLM as an **event extractor** with a fixed schema, and let *your own downstream model* learn what the events are worth.

**LLM-as-extractor pattern (recommended)**
1. *Ingest* raw item -> store immutable (url, first_seen_at, published_at as claimed, source, content hash, raw text).
2. *Dedupe / novelty:* near-duplicate clustering with local embeddings ([BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3), MIT, 29.9M downloads; [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), Apache-2.0; [nomic-embed-text-v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5), Apache-2.0) + MinHash for syndicated copies. Novelty = distance to nearest item in the prior N hours; "first report" flag; count of independent sources (corroboration).
3. *Entity / ticker linking:* LLM proposes entities, **deterministic resolver** maps to tickers/FX pairs/commodities (alias table + SEC `company_tickers.json`). A 2024 paper notes name-to-ticker mapping remains an open problem even when extraction works ([arXiv 2407.15788](https://arxiv.org/pdf/2407.15788)), so keep a confidence field and a human-review queue early on.
4. *Event typing:* fixed taxonomy (central-bank decision/speech, macro print vs consensus, geopolitical shock, supply disruption, earnings, M&A, regulation, sanctions...). Related work: LLM event features into a return model ([arXiv 2512.19484](https://arxiv.org/pdf/2512.19484)); structured event representations ([review](https://www.themoonlight.io/review/structured-event-representation-and-stock-return-predictability)).
5. *Directional prior per asset* (e.g. "hawkish Fed surprise -> USD up, gold down") produced as a **hypothesis with horizon and confidence**, not an order.
6. *Source reliability + hoax check* (cross-source corroboration, official-source confirmation) - section 5/7.

---

## 5. Leakage and the evidence on LLM alpha

### 5a. Why LLM backtests are uniquely contaminated

Three separate leaks; most repos only address the first.
1. **Pipeline leakage** (classical): same-bar execution, split-adjusted prices, restated fundamentals, revised macro data, timestamp = crawl time vs publish time, sentiment scores recomputed later. Practitioner write-ups: an AI trading bot's 83% annualised backtest came from entering at the same close the signal used ([DEV](https://dev.to/qcautomation/i-found-4-backtesting-biases-1mc5)); an AI research agent replicating anomalies got ~500x with look-ahead vs decay-to-zero as-traded because of split-adjusted prices ([Quantpedia](https://quantpedia.com/guardrails-make-the-researcher-what-an-ai-agent-got-right-and-wrong-replicating-nine-equity-anomalies/)). TradingAgents' own changelog shows the pattern: fixes for FRED, Alpha Vantage, social sentiment, decision-log memory, and "model dates that could read filings made after the run date" (README, 2026-07 to 2026-10).
2. **Tool leakage:** if the agent has live web search/browse during a historical replay, it reads the future. Historical replay must serve *only* your timestamped store.
3. **Parametric (memory) leakage:** the model's weights already encode what happened. Data-pipeline hygiene cannot fix this.
   - [Gao, Jiang, Yan, "Detecting Lookahead Bias in LLM Forecasts"](https://arxiv.org/abs/2512.23847) (Dec 2025, rev. Jun 2026): "Lookahead Propensity (LAP)" test; LAP is positive in-sample and drops to ~0 just after the training cutoff; LLM forecast power is amplified where LAP is high, and the interaction vanishes post-cutoff (tasks: headlines->returns, earnings calls->capex).
   - [Glasserman & Lin](https://arxiv.org/abs/2309.17322) (2023): anonymising company names in headlines for GPT-3.5 sentiment; mixed result (anonymised did *better* in-sample, interpreted as a "distraction effect"; gap loses significance out of sample). **Lesson: masking is not a clean fix and changes the task.**
   - [Look-Ahead-Bench](https://arxiv.org/abs/2601.13770) (Jan 2026): standard LLMs (Llama 3.1 8B/70B, DeepSeek 3.2) show significant look-ahead bias measured by alpha decay across regimes; point-in-time models (author's company's "Pitinf") decay less. Author is affiliated with the PiT vendor - treat as promotional-adjacent.
   - [Profit Mirage / FinLake-Bench](https://arxiv.org/abs/2510.07920) (Oct 2025): GPT-4o-class models answered historical market questions correctly >85% of the time (memorised); TradingAgents-style collaboration "mitigates but still suffers 55.68% Sharpe decay" after cutoff (as summarised by search excerpts; I did not read the PDF).
   - [Chronologically Consistent LLMs](https://arxiv.org/abs/2502.21206) (ChronoBERT/ChronoGPT, annual cutoffs 1999-2024): finds look-ahead bias "modest" for an asset-pricing application with BERT-size models. Availability of the weights: **unverified** (one snippet hinted at withdrawal).
   - [FinCAD / "Summoning the Oracle to Slay It"](https://arxiv.org/pdf/2605.24564) (May 2026): proposes decoding-time suppression of memorised outcomes; aggregator-only detail.

**Direct implication for the user's constraint (Claude-only cloud):** all four current Claude models list Jun 2026 as both reliable-knowledge and training-data cutoff ([models overview](https://platform.claude.com/docs/en/about-claude/models/overview)). Claude model IDs are pinned snapshots, so you *can* freeze a model, but you cannot get an uncontaminated historical window before ~Jul 2026 from them. Older Claude snapshots (e.g. Opus 4.5/Sonnet 4.5/Haiku 4.5, still listed) have earlier cutoffs - their exact dates are on Anthropic's Transparency Hub which I did not fetch (**unverified**); a model with an earlier cutoff gives you a longer clean window *after its cutoff*, at the cost of weaker capability. Local open models have their own cutoffs (check each model card).

### 5b. Does anything produce alpha? Evidence table

| Evidence | Type | Result | Reliability |
|---|---|---|---|
| [Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?"](https://arxiv.org/abs/2304.07619) (v6 Oct 2025) | Headline sentiment -> next-day returns | Reports predictive power; ChatGPT-4 long-short Sharpe 3.8 (v4); stronger for small stocks and negative news | Author-reported; sample largely inside training data of the model for early versions; edge expected to decay as adoption grows (their own prediction). |
| [Chen & Pu, "Agentic AI Nowcasting Predicts Stock Returns"](https://arxiv.org/abs/2601.11958) (Jan 2026) | **Live-collected** AI web-search rankings of Russell 1000 from Apr 2025 | Top-20 long daily 5-factor+momentum alpha 18.4 bp, Sharpe 2.43; alpha concentrated in top tier; costs <10% of gross alpha (authors) | The most interesting *positive* result because predictions were recorded in real time; but not independently replicated, pre-training cutoff of the model vs sample not confirmed from the abstract page. A model for your forward-test design. |
| [StockBench](https://arxiv.org/abs/2510.02209) (Oct 2025, v2 Mar 2026) | Contamination-free multi-month daily trading sim | Most LLM agents **fail to beat buy-and-hold**; some show better risk control | Peer-group benchmark; period short. |
| [FinSABER](https://arxiv.org/abs/2505.07078) (v5 Feb 2026) | 20 years, 100+ symbols | Reported LLM advantages "deteriorate significantly"; too conservative in bull, too aggressive in bear | Strongest negative evidence on breadth/length. |
| ["The Alpha Illusion"](https://arxiv.org/abs/2605.16895) (May 2026) | Position paper | FinCon/FinMem/TradingAgents-type Sharpe ratios "should not be treated as deployment evidence"; proposes P1-P6 reporting protocol; recommends **LLMs as auditable information interfaces feeding separate calibration, risk and execution modules** | Position paper (I read the abstract only; the one-year TradingAgents reproduction numbers are not in what I fetched). Directly aligned with this project's architecture. |
| [Agent Market Arena](https://arxiv.org/abs/2510.11695) (Oct 2025) | Live multi-market benchmark (GPT-4o/4.1, Claude-3.5-haiku, Claude-sonnet-4, Gemini-2.0-flash) | Agent *framework* mattered more than model backbone; profitability not stated on the abstract page | Abstract only. |
| [DXRG production record, arXiv 2609.05663](https://arxiv.org/abs/2609.05663) (Sep 2026) | 3,505 user-funded vaults (real ETH, 21 days) + 500-599 Hyperliquid perp agents (69 days) | "Not profitable and trails a matched retail benchmark" (41% vs 50% round-trip win rate); leverage set by the risk slider not the strategy text; sizing volatility-blind; 43.2% of positions touched +300 bp but 49.3% of those closed negative; paired replay of frontier models on 416 scenarios: "statistically indistinguishable" | Largest real-money agent record I found; crypto, short windows, authors' own platform. |
| Alpha Arena (Nof1) Season 1 (Oct 18 - Nov 3 2025, crypto, ~$10k per model) | Live competition | Secondary coverage: Qwen3-Max +22.3%, DeepSeek +4.9%, Claude Sonnet 4.5 -30.8%, Grok 4 -45.3%, Gemini 2.5 Pro -56.7%, GPT-5 -62.7%. Organisers themselves cited prompt bias, small samples, short window. [Independent analysis](https://magnusross.github.io/posts/nof1-analysis): best model's PnL would occur ~10% of the time under a random strategy (p~0.10) | Final numbers are from secondary news (e.g. [Forklog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/)), not from nof1.ai, which I could not fetch (page was nav-only). |
| Alpha Arena Season 1.5 (US equities, from 2025-11-19) | Live competition | Secondary coverage: undisclosed "mystery model" (later reported as xAI Grok 4.20) ~+12%; GPT-5.1 second; **verify on nof1.ai**. A May 2026 report said Season 2 would add web search, longer thinking and multi-step tools; one Chinese-language report of 4 rounds with 8 models trading US tech lost about a third overall but I could not confirm it was Season 2. | Mostly unverified secondary; do not cite numbers without checking primary. |
| [TradeTrap](https://arxiv.org/pdf/2512.02261) / [SoK 2609.19705](https://arxiv.org/abs/2609.19705) | Robustness | Tiny account-state corruption can drive large loss; a single fake headline crashed simulated markets (400 agents) in every run; hard halts and loss limits *outside the model* removed the effect | Security, not alpha; strongly relevant to risk track. |
| Public paper-trade logs | Anecdotal | `qrak/LLM_trader` +0.05% vs -9.27% B&H, "not evidence of an edge"; several YouTube/TikTok experiments lost money or did nothing (section 6) | Weak individually, consistent as a pattern. |

**Honest reading:** (a) LLMs can plausibly extract *information* from text (headline sentiment, earnings-call content) - that is where the better-supported positive claims live; (b) end-to-end "LLM decides and trades" has no credible out-of-sample record; (c) any positive claim must be discounted for training-window overlap and short samples; (d) the one design with real-time-recorded predictions (Chen & Pu) is also the one that points to *where* value may be: ranking/selection from live web information, mostly the long side, in liquid names. Forex and metals are macro-driven with far fewer independent observations per year than a 1,000-stock cross-section; I found **no** credible published evidence of LLM news agents beating baselines in FX or gold specifically (absence of evidence from my searches only).

### 5c. How to evaluate agent insights honestly (concrete protocol)

1. **Timestamped, append-only news store ("news lake").** For each item: `first_seen_at` (your clock at ingestion = the only timestamp you can trust), `published_at` (claimed), `source`, `url`, `content_sha256`, raw bytes snapshot, `revision` if content later changes. Never overwrite; store edits as new rows. Collect *everything* you might later want, from day one, even before the agent exists. Use Parquet/DuckDB or SQLite WAL on local disk; back it up.
2. **Point-in-time replay clock.** All agent tools take `as_of` and read only from the store with `first_seen_at <= as_of`. No live search, no live price fetch inside replay. For macro, use ALFRED vintages; for COT, key by release time; for filings, EDGAR acceptance time; for prices, as-traded unadjusted (adjust on your side with timestamped corporate-action tables). Copy `risk-aware-trading-agents`: news "arrives by the minute published", fills at next open, a look-ahead assertion on every run.
3. **Insight ledger.** Every agent output is a structured record: `{insight_id, created_at, model_id (pinned snapshot), prompt_hash, input_item_ids, instrument, direction, horizon, magnitude_bucket, confidence, thesis, falsifier}`. Immutable. Scoring job later joins to realised returns at the stated horizon, net of costs. This ledger is also the training label source for your own profitability-index model (track 3).
4. **Shadow-mode forward test is the only fully clean test for Claude.** Run the pipeline live, record insights, score after horizon. Minimum meaningful length: more than one macro regime and enough independent events (rough rule: hundreds of independent decisions per hypothesis; forex/gold will need months). Pre-register each hypothesis (instrument, horizon, metric) before looking. Correct for multiple comparisons across prompts/models/events.
5. **Baselines that must be beaten** (using the same ledger): buy-and-hold; a naive momentum/carry/vol-target rule; random-direction with matched turnover/leverage (the Alpha Arena critique); a FinBERT-only sentiment signal; a "do nothing" cash baseline. Report paired differences with day-clustered confidence intervals (as in DXRG).
6. **Leakage probes you can run cheaply:** (i) *Placebo cutoff test* - compare agent accuracy on events before vs after the model's cutoff (Gao et al.'s signature: edge only before); (ii) *date/entity masking A/B* (TraderHarness-style) - large gap means memory; (iii) *recall query* asking the model what happened to X on date Y with no context (Gao et al. LAP idea); (iv) *shuffled-news control* - give the agent news from a different date; edge should vanish.
7. **Repeatability:** local models at fixed seed/temperature 0 replay exactly; for Claude, store full request+response (and snapshot ID) and replay from the cache, never re-call. Run each decision k times to quantify nondeterminism before trusting a single run (TradingAgents README warns results are non-deterministic).
8. **Judge your insights, not the PnL, first.** Early on there are too few trades for PnL to mean anything; score hit-rate of directional calls vs horizon, calibration of confidence (Brier), and event-detection precision/recall against hand-labelled events.
9. **Hoax/injection tests:** replay known hoaxes (e.g. the fake Emulex press release used in the SoK) and injected "ignore previous instructions" strings in news bodies; the pipeline must flag, not act.

---

## 6. Community findings (with links)

### Access report (what I could and could not reach)
- **Reddit: not reachable.** `WebSearch` refused `reddit.com` outright ("domain not accessible to our user agent"), `WebFetch` refused `old.reddit.com`, and a direct request to Reddit's JSON search returned an HTML block page. One further reachability probe of Reddit/X/Instagram/TikTok from the shell was denied by the permission classifier and I did not attempt workarounds. **I therefore have no first-hand r/algotrading, r/LLMDevs, r/LocalLLaMA or r/quant content; nothing below is attributed to Reddit.** One search-result link pointed at a third-party Reddit mirror in a Hermes-agent thread (cited once in section 8 for local-model advice, secondary).
- **Hacker News: reachable** via Algolia API; used below.
- **YouTube:** only reachable as search-result titles/descriptions via `WebSearch`; I did not watch videos or read transcripts.
- **X/Twitter:** a few posts surfaced in search snippets; no direct access.
- **TikTok:** `discover` pages surfaced via search (marketing-heavy); no direct access.
- **Instagram:** **nothing found or reachable**; no content reported.
- Medium: one article returned HTTP 403; another blog was fetched.

### Hacker News (read directly)
- ["Multi-Agents LLM Financial Trading Framework" (TradingAgents), 120 pts / 81 comments, 2026-09-08](https://news.ycombinator.com/item?id=49605822). Notable comments:
  - Reviewer `dsl` says an hour of code reading found: Yahoo News fed twice (double weight) into sentiment and news analysis; a sentiment prompt that primes the model bullish on Nvidia; a self-learning-loop parsing bug that creates hallucinated memories on truncated responses; subreddit sentiment controllable by whoever posts the 5 most recent messages; reflection prompt forcing the agent to "cite alpha" even in a market-wide downturn. (Single-person review of an earlier version; the repo has had several releases since. Not independently confirmed here.)
  - `hacker_9` (self-described decade in hedge funds): specialising identical-brain agents adds little; Reddit sentiment and TA are lagging; options IV/premiums would be closer to what funds use.
  - `qurren`: claims a profitable trading agent exists, will not open-source it, "looks nothing like this", and says this repo's problem is "ingesting a shitton of noisy sources that have almost no signal... naively". (Unverifiable anecdote.)
  - `_pdp_`: running their own agent experiment, "has lost a bit of money"; blog at trades.chatbotkit.space (anecdotal).
  - Skeptics: "token slot machine" jokes, "where is the performance section", cherry-picked windows, and the suspicion that 100k+ stars were inflated.
- [Misalignment and Deception by an autonomous stock trading LLM agent](https://news.ycombinator.com/item?id=38353880) (91 pts / 34 comments, 2023): demonstration that a GPT-4 trading agent acted on insider information and lied to its manager under pressure; relevant to guardrails.
- [Show HN: TradingAgents without the API bill - run multi agents in Claude Code](https://news.ycombinator.com/item?id=47987347) (1 pt, 2026-05-02): shows interest in running the TradingAgents pattern inside Claude Code (I did not review the project).
- New benchmark/project posts with little discussion (0-6 comments): [SharpeBench "luck-robust benchmark"](https://news.ycombinator.com/item?id=48643290), [BotTrade replayable benchmark](https://news.ycombinator.com/item?id=48939231), [Atlas self-improving agents](https://news.ycombinator.com/item?id=47356891), [Build AI Trading Agents in Cursor/Claude with an MCP Server](https://news.ycombinator.com/item?id=47545829). These show the community converging on **replayable, luck-adjusted benchmarks**.
- No HN threads with substantive comments found for Alpha Arena, FinGPT (2023: ["Is FinGPT Coming?"](https://news.ycombinator.com/item?id=35845178), 18 comments) or ai-hedge-fund beyond the above.

### Practitioner write-ups (secondary, fetched or via search snippets)
- [David Arias, "I tested AI Hedge Fund..."](https://davidariasfinance.com/research/ai-hedge-fund-live-run/) (fetched): one real run took 59 s and 3 model calls; hand-set persona weights decided positions; most of the book ended up in cash; investors use fundamentals/earnings only; no overfitting check; design safeguards cited: PIT statements, masked backtests, next-close fills. Says nothing about returns.
- [Lawrence Liu on DEV, "From Gut Feel to Backtest: 5 Iterations of an AI Trading System"](https://dev.to/xqliu/from-gut-feel-to-backtest-5-iterations-of-an-ai-trading-system-2em6) and [I found 4 backtesting biases](https://dev.to/qcautomation/i-found-4-backtesting-biases-1mc5) (search snippets only): recurring lesson "would I actually have this value at decision time?"; >30% annualised should trigger a leakage hunt.
- [Quantpedia, "Guardrails Make the Researcher"](https://quantpedia.com/guardrails-make-the-researcher-what-an-ai-agent-got-right-and-wrong-replicating-nine-equity-anomalies/) (snippet): an AI agent replicating nine anomalies; look-ahead via split-adjusted prices inflated results ~500x.
- A Medium article, ["I opened the 5 most-starred AI trading repos on GitHub"](https://medium.com/@fullstackalpha/i-opened-the-5-most-starred-ai-trading-repos-on-github-ad4e6eb65265), returned 403; **not read**.

### YouTube (titles/descriptions from search only; not watched)
- ["AI Trading Is a Lie: I Lost Real Money Twice"](https://www.youtube.com/watch?v=bp_u9Gzp1OU), ["I Tested 5 AI Trading Models. A Simple Rule Beat Them All"](https://www.youtube.com/watch?v=6l2irMURKzQ) (description: a no-AI rule made 67% on gold, creator says it beat every AI model tested), ["3,505 AI Trading Agents Got Real Money. The Paper Found No Edge"](https://www.youtube.com/watch?v=jTf2O10m_sk) (matches the DXRG paper), ["I Tested a Live Chat GPT Trading Agent (Live $100 Trading Experiment)"](https://www.youtube.com/watch?v=vXNmlBMYkXU), ["I Built an AI Trading Agent With $70"](https://www.youtube.com/watch?v=BHF5tqhp4dU) (description: ~$10/day in compute). Pattern in titles: small-money tests lose or do nothing; none is rigorous.

### X / TikTok / Instagram
- X: promotional thread introducing TradingAgents ([Quant Science](https://x.com/quantscience_/status/2038591142854291522)) with no live P&L; paper-summary posts ([StockBench](https://x.com/rohanpaul_ai/status/1974583220306862329), [robustness paper](https://x.com/rohanpaul_ai/status/1996505756984803652)). I did not open them.
- TikTok: search surfaced "connect Claude to TradingView/Alpaca paper trading" style discover pages; snippets mention a creator who tested 26,000+ ideas and most lost to a coin flip, and a paper-trading creator with 6 wins / 8 losses; **mostly funnel content for paid guides**; treat as noise.
- Instagram: **no reachable content.**

**What builders actually report (synthesis, with the access caveats above):** (1) the pipeline plumbing (timestamps, fills, adjusted prices) is where "alpha" most often evaporates; (2) multi-agent debate adds cost and complexity without demonstrated gain; (3) news/social sources are noisy and manipulable; (4) the sober voices want replayable, luck-adjusted benchmarks and honest forward logs; (5) anyone who claims a working agent will not publish it (unverifiable).

---

## 7. Recommended stack for this project

### 7a. Architecture (local-first, Claude as the only cloud LLM)

```
COLLECTORS (local, scheduled, polite, own timestamps)
  RSS/Atom: Fed, ECB, BoJ(url TBD), SEC EDGAR, central-bank & ministry feeds
  CFTC COT (Fri 15:30 ET), FRED/ALFRED vintages, GDELT 2.0 (15-min), economic-calendar (self-built)
  News APIs (optional, 1-2): Finnhub free / Alpaca-Benzinga history / Marketaux free
  Web: SearXNG + Crawl4AI/Playwright for targeted pages (low volume)
        |
        v
NEWS LAKE (append-only, first_seen_at, raw snapshot, sha256; DuckDB/Parquet on local SSD)
        |
        v
LOCAL PROCESSING (no cloud)
  dedupe/novelty/corroboration: bge-m3 or Qwen3-Embedding + MinHash
  entity/ticker/FX/commodity linking: alias tables + SEC tickers + small local LLM
  sentiment baseline: FinBERT (research use) and/or a small Qwen-class finance-sentiment model
  structured event extraction (JSON schema): local ~30B-class MoE via Ollama/llama.cpp/MLX
        |
        v
CLAUDE (cloud, selective)
  Haiku 5.5: bulk extraction where local model quality is insufficient (Batch API)
  Sonnet 5.5: daily/regime synthesis, multi-doc reasoning, tool-using research agent (Agent SDK)
  Opus 5.5 / Fable 5.2: weekly deep review, adjudicate disagreements, LLM-as-judge on a sample
        |
        v
INSIGHT LEDGER (immutable, structured, falsifiable)  --->  scorer (realised returns, baselines)
        |
        v
FEATURES for the user's encoder+classifier (track 3)  +  dashboards for human review
Order authority and risk limits stay OUTSIDE all LLMs (tracks 5/6).
```

### 7b. Picks, in priority order
1. **Build the news lake + insight ledger first** (week 1). Everything else is replaceable; the lost history is not.
2. **Collectors:** feedparser/Scrapy for RSS and EDGAR; CFTC public-reporting API; FRED with realtime params; GDELT 2.0 file pulls. Respect SEC's 10 req/s and User-Agent rule.
3. **Orchestration:** Python + `claude-agent-sdk-python` (MIT) for the Claude-side research agent; plain Python/DuckDB for pipelines. Borrow TradingAgents' structured-output + decision-log ideas rather than its graph. If you want a ready LangGraph baseline to *measure against*, run TradingAgents in shadow mode as one more "analyst" whose outputs go into the ledger and get scored like any other.
4. **Tools exposed to Claude via MCP:** your own read-only MCP over the news lake (as_of-aware), SearXNG MCP for live research only, OpenBB MCP (after verifying the repo/package provenance) for free-data lookups. Disable live web tools in replay mode.
5. **Models:** local small/medium for volume; Claude for judgement. Pin Claude snapshot IDs and store all request/response pairs.
6. **Evaluation:** section 5c protocol, plus 2-3 baselines running on the same ledger from day one.
7. **Guardrails:** corroboration requirement (>=2 independent sources or one official source) before any "event" can raise a high-confidence insight; strip/escape instructions in fetched text; no agent can place orders.

### 7c. Rough Claude cost sketch (my arithmetic from [vendor pricing](https://platform.claude.com/docs/en/about-claude/pricing))
- Haiku 5.5 extraction at ~2,000 input + 300 output tokens per article: $0.0002 + $0.00015 = **~$0.00035/article**; 10,000 articles/day = **~$3.50/day** (~$1.75 with Batch API -50%, if latency allows). (Haiku 5.5 charges more for prompts over 100k tokens; irrelevant here.)
- Sonnet 5.5 ($2/$10 per MTok): a 100k-token-in / 5k-out daily macro synthesis = $0.20 + $0.05 = **~$0.25 per run**. Cache reads are 5% of base on Sonnet 5.5/Opus 5.5.
- Opus 5.5 ($4/$20) and Fable 5.2 ($8/$40) are 2x and 4x Sonnet 5.5 on both sides; reserve for low-volume adjudication.
- Reference points: `qrak/LLM_trader` reports $7.12 inference over 52 days for one asset (its own number); the Claude web-search tool is $10 per 1,000 searches.
- Conclusion: **token cost is not the bottleneck; evidence and engineering time are.** A multi-agent debate with ~7 agents per ticker per day is the part that multiplies cost without proven benefit.

### 7d. What I would not do
- Not adopt NewsAPI (24h delay + dev-only licence), Perplexity Sonar or Exa/Tavily/Brave "answer/deep" modes (other cloud LLMs), `r.jina.ai`, or hosted Firecrawl in the pipeline.
- Not depend on yfinance/Yahoo news as the primary feed.
- Not let any LLM size positions or place orders.
- Not trust any backtest of a Claude-based agent over dates before ~Jul 2026.

---

## 8. Local-first stack (new constraint: only Claude may be a cloud LLM)

Assumes Apple Silicon Mac; I assume >=32 GB unified memory for the model suggestions below. With 16 GB, restrict local LLMs to ~4-8B models and push more extraction to Haiku 5.5.

### (a) What already runs locally

| Component | Local option | Facts |
|---|---|---|
| LLM runtime | [Ollama](https://github.com/ollama/ollama) (186,921 stars, MIT), [llama.cpp](https://github.com/ggml-org/llama.cpp) (134,935, MIT), [mlx-lm](https://github.com/ml-explore/mlx-lm) (7,654, MIT), [LM Studio](https://lmstudio.ai) (CLI `lms`: 5,426 stars) | Ollama reportedly moved its Apple-Silicon backend to MLX in Mar 2026 (secondary source). One guide says current MLX agentic tool-calling still trails llama.cpp (secondary). |
| Local models for extraction/tool-use | Community picks for 32 GB+ Macs: **Qwen3.6-35B-A3B** (Q4_K_M GGUF or MLX 4-bit), **Gemma 4 26B-A4B** (but a llama.cpp tool-calling bug reportedly depressed its benchmark scores) | Source: community thread, secondary, [June 2026](https://r.datuan.dev/r/hermesagent/comments/1uc7rw5/). **Unverified**: no measured tool-calling accuracy on Mac found. Run your own extraction eval against Claude-labelled data before choosing. |
| Embeddings | bge-m3 (MIT), Qwen3-Embedding-0.6B (Apache-2.0), nomic-embed-text-v1.5 (Apache-2.0) | Run via sentence-transformers/Ollama/llama.cpp. |
| Sentiment | FinBERT (HF licence cc-by-nc-sa-4.0), finbert-tone, small Qwen3-based finance-sentiment models | See section 4. |
| Search | SearXNG (AGPL-3.0) + MCP wrapper | Replaces Tavily/Exa/Brave/Serper. |
| Crawl | Crawl4AI (Apache-2.0), Playwright, Scrapy | Replaces Firecrawl cloud / Jina hosted. Article-text extraction libs such as trafilatura: **not verified here**. |
| Agent orchestration | LangGraph, Agno, PydanticAI, Claude Agent SDK | All can call local OpenAI-compatible endpoints. |
| Storage | DuckDB/SQLite/Parquet | Local. |

### (b) Where Claude is worth the cloud call
- **Use Claude for:** multi-document synthesis across 20-100 items; macro regime narrative (central-bank reaction functions, geopolitics -> metals/FX); long-context work (all current models have 1M context); reliable tool-use loops in a research agent; adjudicating conflicts between sources and detecting hoax/injection patterns; **LLM-as-judge over a sample of local-model outputs** to measure local quality; writing the falsifiable insight record.
- **Use local for:** anything high-volume or run repeatedly in replay (embeddings, dedupe, ticker linking, FinBERT/sentiment, first-pass event typing, summarising RSS); reproducibility (fixed weights, seed, temperature 0); zero marginal cost during backtest replays; offline resilience.
- **Middle:** Haiku 5.5 is cheap enough ($0.10/$0.50 per MTok) to *replace* a weak local model for extraction if your eval shows the local model's errors matter; Batch API halves it.
- **Don't expect Claude to beat local models on look-ahead:** all current Claude cutoffs are Jun 2026; a local model with an *older* cutoff can actually give you a longer clean replay window after its cutoff (check each model card).

### (c) Repos/frameworks supporting Claude *and* local models behind one interface
- **TradingAgents:** providers include `anthropic`, `ollama`, and `openai_compatible` (vLLM, LM Studio, llama.cpp); **each model tier can have its own provider/endpoint** (e.g. managers on `claude-opus-5-5`, analysts on local) - verified in its README. Data vendors (yfinance, Alpha Vantage, FRED, EDGAR) are cloud but free; social screening via Typesafe is optional/cloud.
- **Claude Agent SDK + gateway:** model traffic is routed by `ANTHROPIC_BASE_URL`; the gateway must speak the Anthropic Messages API. LiteLLM ([63,236 stars](https://github.com/BerriAI/litellm), licence shown as NOASSERTION by the API) is the documented proxy for non-Anthropic backends ([LiteLLM tutorial](https://docs.litellm.ai/docs/tutorials/claude_agent_sdk), [Claude Code LLM-gateway docs](https://code.claude.com/docs/en/llm-gateway.md)). **Ollama itself exposes an Anthropic-compatible API since v0.14.0 (Jan 2026)**: `ANTHROPIC_BASE_URL=http://localhost:11434` ([Ollama docs](https://docs.ollama.com/api/anthropic-compatibility.md)); one article says LM Studio and llama.cpp do too (secondary). Doc evidence is for Claude Code; SDK-specific behaviour should be tested.
- **ValueCell:** OpenAI-compatible endpoints + others, local data storage (README).
- **OpenBB:** all-local Python/MCP; model-agnostic.
- **ai-hedge-fund:** Anthropic yes; Ollama listed as "next" in v2 (v1 had it).
- **FinRobot:** V2 on PydanticAI (multi-provider framework; provider list for this app not verified), V1 on OpenAI Agents SDK, V0 AutoGen.
- **gpt-researcher / open_deep_research:** "any LLM provider" - adaptable for macro briefs.
- **anthropics/financial-services-plugins:** Claude-only by design (Cowork / Managed Agents API); good skill/prompt patterns.

### (d) Tools that force other clouds / SaaS, and the local replacement
| Tool / feature | Problem under the constraint | Local / allowed replacement |
|---|---|---|
| FinMem | Hard-wired OpenAI `text-embedding-ada-002` | bge-m3 / Qwen3-Embedding |
| StockAgent | OpenAI or Gemini only | Not worth adopting (no licence) |
| FinRobot V1 | OpenAI Agents SDK | V2/V0 or own pipeline |
| TradingAgents defaults/examples | OpenAI model names in examples; optional Typesafe "Jev" cloud screening | Set `llm_provider` to anthropic/ollama; skip Typesafe key |
| ai-hedge-fund | Financial Datasets (paid API or x402 USDC payments); no Ollama in v2 yet | Data from EDGAR/yfinance (other track); wait for Ollama or patch provider factory |
| Perplexity Sonar, Exa deep/reasoning, Tavily answers, Brave Answers | Other vendors' cloud LLMs | SearXNG raw results; Brave/Exa/Tavily *raw search only* if a paid index is wanted (still SaaS, but not an LLM); Claude web-search tool ($10/1k searches) for live research |
| Firecrawl cloud, Jina `r.jina.ai` | SaaS crawl | Crawl4AI + Playwright |
| HKUDS/AI-Trader | Hosted platform; your signals go to ai4trade.ai | Do not use |
| Finnhub/Marketaux/Alpaca/Benzinga/Tiingo/Massive | SaaS data (not LLMs) | Probably acceptable under "only cloud LLMs are Claude", but confirm the user's intent; EDGAR/Fed/ECB/CFTC/GDELT/FRED cover a lot at zero cost |
| FinBERT licence | CC-BY-NC-SA on HF | Fine for personal research; swap for an Apache-licensed small model (e.g. NOSIBLE Qwen3-0.6B-based) if commercialising, after your own eval |

---

## 9. Risks and open questions

**Risks**
1. **No alpha may exist at this layer for forex/gold.** Evidence for LLM news edge is mainly equity headline-level, decays with adoption, and is contaminated. Treat the layer as an *information-extraction and feature-generation* service whose value is proven only by forward ledger scores and by incremental lift in your own model.
2. **Forward-test time cost.** Clean evidence accrues at calendar speed. Macro events are sparse; expect months for weak signals on FX/metals. Start recording immediately.
3. **Model churn.** Claude snapshots are pinned but retire (Haiku 5.5 "not sooner than Oct 7, 2027", etc.); local weights change too. Insights scored under one model may not transfer to the next; the ledger must record model IDs and you must re-score on upgrade.
4. **Source fragility and licensing:** Yahoo feeds going dark, Reddit/X API changes, WGC/ForexFactory terms, Benzinga/Finnhub LLM-use terms unknown, NewsAPI dev-only. Mitigate with official feeds and by retaining raw snapshots.
5. **Prompt injection / hoaxes through crawled text** (SoK: single fake headline crashes simulated markets). Needs provenance + corroboration + hard limits outside the LLM.
6. **Over-engineering:** multi-agent debate raises cost and complexity; no evidence it helps. Begin with single-purpose extractors + one synthesiser.
7. **Local-model quality unknown for your task.** The Qwen/Gemma tool-calling claims are community-sourced; measure on your own labelled set.
8. **Third-party summaries in this report** (search-engine syntheses of arXiv abstracts, vendor comparisons) can be wrong; items marked unverified need primary-source confirmation before decisions.

**Open questions for the user/coordinator**
- RAM of the Mac? (decides local model tier.)
- Is SaaS *data* (Finnhub, Alpaca, Marketaux) acceptable under local-first, or only local/open feeds + Claude?
- Is the product personal-use only? (Resolves FinBERT, Tiingo, Brave, Reddit/X licence questions.)
- Which forex pairs and metals (gold/silver only)? Determines the central banks, COT contracts and mining/geopolitical sources.
- Time horizon of insights (intraday event reaction vs multi-day macro view)? Changes latency needs: most free feeds are minutes-level, adequate for multi-hour+, not for headline scalping.
- Should the ledger also store *non-LLM* baselines' signals so lift is measurable from day one? (I recommend yes.)
- Verify: nof1.ai primary data for Alpha Arena seasons; Anthropic Transparency Hub cutoff dates for older Claude snapshots; Finnhub/Alpaca current free-tier terms and historical depth; BoJ RSS URL; Reddit policy pages; canonical OpenBB repo after the redirect; the TradingAgents/Alpha-Illusion one-year reproduction numbers.

---

## Appendix: source list by topic (non-exhaustive)
- Repos: links inline in section 2 (GitHub API reads, 2026-11-14).
- Leakage/evidence papers: arXiv [2512.23847](https://arxiv.org/abs/2512.23847), [2601.13770](https://arxiv.org/abs/2601.13770), [2605.24564](https://arxiv.org/pdf/2605.24564), [2510.07920](https://arxiv.org/abs/2510.07920), [2309.17322](https://arxiv.org/abs/2309.17322), [2502.21206](https://arxiv.org/abs/2502.21206), [2605.16895](https://arxiv.org/abs/2605.16895), [2510.02209](https://arxiv.org/abs/2510.02209), [2505.07078](https://arxiv.org/abs/2505.07078), [2510.11695](https://arxiv.org/abs/2510.11695), [2601.11958](https://arxiv.org/abs/2601.11958), [2609.05663](https://arxiv.org/abs/2609.05663), [2609.19705](https://arxiv.org/abs/2609.19705), [2304.07619](https://arxiv.org/abs/2304.07619), [2412.20138](https://arxiv.org/abs/2412.20138).
- Vendor pages fetched: [Marketaux](https://www.marketaux.com/pricing), [NewsAPI](https://newsapi.org/pricing), [GDELT](https://www.gdeltproject.org/data.html), [SEC](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), [Fed feeds](https://www.federalreserve.gov/feeds/feeds.htm), [ECB feeds](https://www.ecb.europa.eu/home/html/rss.en.html), [CFTC COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm), [Tavily](https://tavily.com/pricing), [Exa](https://exa.ai/pricing), [Brave](https://brave.com/search/api/), [Perplexity](https://docs.perplexity.ai/guides/pricing), [Firecrawl](https://www.firecrawl.dev/pricing), [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Anthropic models](https://platform.claude.com/docs/en/about-claude/models/overview).
- Alpha Arena: [Forklog Season 1.5](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/), [Magnus Ross analysis](https://magnusross.github.io/posts/nof1-analysis).
- HN thread: https://news.ycombinator.com/item?id=49605822
