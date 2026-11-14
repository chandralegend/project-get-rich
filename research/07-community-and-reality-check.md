# 07 - Community Scan and Reality Check

Track: cross-cutting community scan, end-to-end projects, live LLM-trading experiments, retail-outcome evidence, scams, realistic edge.
Date of research: 2026-11-14. Author: research agent 7 of 7.
Constraint added mid-task by the coordinator: the project is LOCAL-FIRST (only Anthropic Claude as a cloud LLM; everything else local on an Apple Silicon Mac). A "Local-first fit" column and a "Local-first stack" section are included.

Conventions used in this report:
- "Verified" means I fetched the source myself in this session (GitHub API via `gh api`, WebFetch, or Algolia API). "Secondhand" means I only saw it via a search-engine summary or a third-party article. "Unverified" means I could not confirm it. Figures I could not verify are labeled.
- GitHub star counts and "last push" dates were pulled from the GitHub REST API on 2026-11-14. "Last push" is `pushed_at` (any branch), not necessarily the last commit on the default branch.
- Coverage marks: `●` substantial, `◐` partial or shallow, `○` none. These are my judgment from READMEs and repo metadata. I did not install or run any of these projects.

---

## 1. TL;DR (blunt)

1. **No public evidence that an LLM trading agent has a durable, cost-adjusted edge.** The best-run public experiments (Alpha Arena, StockBench, Flat Circle's survey of 11 arenas) show noisy results where the median model loses or fails to beat buy-and-hold. A May 2026 position paper that re-ran TradingAgents (the most-starred project in the space) with realistic costs found its Sharpe fell from 0.43 to 0.22 (secondhand abstract summary; arXiv 2605.16895).
2. **The open-source landscape is huge in stars and thin in substance.** TradingAgents has 122k stars, virattt/ai-hedge-fund 65k, daily_stock_analysis 72k. Several of the biggest ones are explicitly "educational, not for real trading." Stars are not a quality signal. Kronos has 47.8k stars and its last push was 2026-04-13.
3. **Nothing covers the user's full plan.** The closest to the vision is Vibe-Trading (agents, backtest, paper, live broker incl. MT5, Claude and Ollama), but it is 7.5 months old and changes daily. Nobody ships an "own encoder+classifier on a profitability index, trained progressively" with leak-safe evaluation and cost-aware promotion gates. That gap is the real opportunity and also the real risk.
4. **Retail base rates are brutal.** UK broker pages fetched today say 69-80% of retail CFD accounts lose money (IG UK 70%, CMC UK 69%, Pepperstone 80%, eToro 55%). Brazil day-trading study: 97% of persistent day traders lost money. Prop-firm challenge pass rates are roughly 10-20% and about 7% of buyers are ever paid (vendor-derived, directional only).
5. **The credible small-player edges are slow and boring**: diversified low-turnover systematic strategies, risk/vol management, LLMs used as an information-extraction layer feeding classical models, and honest cost accounting. Latency-sensitive news trading, intraday FX/gold CFD scalping, and crypto perps with leverage are where small players get eaten.
6. **Local-first is viable for the extraction/summarization layer, not proven for judgment.** Small local models (Qwen3 8B/30B, Llama3 8B, GPT-OSS-20B) are competitive with FinBERT on sentiment in preprints, but reported accuracy on financial NLP tasks is only mid-60s% for the best open model tested. Use Claude for hard synthesis and a local model for bulk extraction, and measure the difference on your own labeled set.
7. **Evaluate on data after each model's training cutoff.** Look-ahead contamination is the single most under-appreciated trap in LLM-for-finance backtests (Look-Ahead-Bench, Alpha Illusion, Glasserman and Lin).

---

## 2. End-to-end project landscape

Stars/last push/license: verified via GitHub API on 2026-11-14. Local-first fit is from READMEs (grep for Ollama/Anthropic/Claude, then read key lines); where I only grep-counted, I say so.

### 2.1 Coverage matrix and local-first fit

Legend for layers: **A** agents/news-insight, **F** forecasting, **M** own trained model, **R** risk/asset mgmt, **B** backtest, **P** paper, **L** live.

| # | Project | Stars | Last push | License | What it does | A | F | M | R | B | P | L | Local-first fit | Maturity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 122,489 | 2026-11-04 | Apache-2.0 | LangGraph multi-agent "trading firm" (analysts, bull/bear debate, trader, risk, PM). Paper: arXiv 2412.20138. v0.3.1 | ● | ○ | ○ | ◐ (risk agent debate only) | ◐ | ○ | ○ | Ollama native (`llm_provider: ollama`), plus any OpenAI-compatible endpoint (vLLM, LM Studio, llama.cpp). Claude supported (also Bedrock). Mixed providers per role. Best local-first fit of the agent frameworks | Research code. README disclaims trading advice. 147 open issues. Independent re-run showed gross-to-net Sharpe collapse (see 3.4) |
| 2 | [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64,662 | 2026-11-09 | MIT | Investor-persona agents (Buffett etc.), TUI app with paper-trading ledgers and backtests | ● | ○ | ○ | ◐ | ◐ | ◐ | ○ | README lists Anthropic, OpenAI, DeepSeek, Google, xAI, Kimi; **no Ollama in current README** (older versions had it per my memory; unverified). Needs a Financial Datasets API key (paid) or a USDC wallet | Self-described "proof of concept", "not intended for real trading" |
| 3 | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 38,189 | 2026-11-13 | MIT | Research agent + quant lab (478 alphas benchmark, backtests across markets, options lab) + paper trading + live under "mandate" with kill switch. Broker matrix includes **mt5, alpaca, ibkr, etoro, binance, okx** (Live: mt5, alpaca, etoro, binance, okx, futu, tiger, robinhood) | ● | ◐ | ○ | ◐ (risk x-ray, exposure limits, kill switch) | ● | ● | ● | **Ollama (no key) and Claude native Messages API, plus a `claude-cli` provider using local Claude Code login.** Check Anthropic terms before using a subscription login as an automated backend (unverified). Docker/PyPI | **Closest to the user's vision.** Created 2026-04-01 (7.5 months old, 38k stars: fast; treat star velocity with suspicion). Very high churn |
| 4 | [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) | 71,909 | 2026-11-14 | MIT | LLM stock analysis dashboard with news and push notifications. Chinese-first, A-share focus | ● | ○ | ○ | ○ | ○ | ○ | ○ | Ollama, Claude, Gemini, DeepSeek, OpenAI-compatible. README says Ollama suits local/Docker deployment | Popular utility, analysis only |
| 5 | [hsliuping/TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | 32,948 | 2026-09-22 | NOASSERTION (unclear) | Chinese enhancement of TradingAgents | ● | ○ | ○ | ◐ | ○ | ○ | ○ | grep: no Ollama/Anthropic mention. License unclear: do not reuse code | Derivative; license ambiguity |
| 6 | [NoFxAiOS/nofx](https://github.com/NoFxAiOS/nofx) | 13,279 | 2026-11-04 | AGPL-3.0 | "AI trading terminal": chart + AI trade plans + approve + Autopilot. Binance/Hyperliquid/OKX/Bitget perps; description mentions stocks, commodities, forex | ◐ | ○ | ○ | ◐ | ○ | ○ | ● | Runs on your machine via Docker, but README routes "AI and data access" through a third-party service (Claw402). No Ollama/Claude mention in README | Commercial-adjacent (Vergex). 518 open issues. Crypto-venue centric. Heavy caution (live leveraged perps) |
| 7 | [OpenByteInc/QuantDinger](https://github.com/OpenByteInc/QuantDinger) | 13,749 | 2026-11-14 | Apache-2.0 | Self-hosted "Agentic Trading OS": AI research, Python strategies, backtest, Alpaca paper | ● | ○ | ○ | ◐ | ● | ◐ | ◐ | README mentions OpenAI 10x, Claude once, no Ollama | Unknown quality; read code before trusting |
| 8 | [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) | 23,263 | 2026-06-11 | API says null (README badge says MIT) | Hosted "agent-native trading platform" (ai4trade.ai); an agent joins by reading a SKILL.md URL; social/copy-trading flavor | ◐ | ○ | ○ | ○ | ○ | ◐ | ◐ | Hosted service dependency. **Onboarding pattern ("send this message to your agent") is the same shape as a prompt-injection vector.** Not local-first | Treat as a social platform, not a framework |
| 9 | [ginlix-ai/LangAlpha](https://github.com/ginlix-ai/LangAlpha) | 2,298 | 2026-11-14 | Apache-2.0 | "Claude Code for financial markets": research agent with market data (stocks, indices, crypto, FX, commodities, options) | ● | ○ | ○ | ○ | ◐ | ◐ | ○ | **Claude (incl. subscription sign-in) and local Ollama / LM Studio / vLLM** | Young, active. Good fit for the "insight" layer |
| 10 | [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 8,416 | 2026-10-24 | Apache-2.0 | Agent platform for equity research reports etc. | ● | ○ | ○ | ○ | ○ | ○ | ○ | OpenAI-centric in README | Research/demo |
| 11 | [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 21,566 | 2026-10-25 | MIT | Open financial LLMs (LoRA fine-tunes for sentiment etc.), data pipelines | ◐ | ○ | ◐ | ○ | ○ | ○ | ○ | Open weights, runs locally. Fine-tuned on older base models | Research; useful as a baseline for local news models |
| 12 | [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 17,068 | 2026-11-03 | MIT | Deep-RL for trading; FinRL-Meta datasets/envs (1,964 stars); FinRL-Trading/"FinRL-X" (3,941 stars, Apache-2.0) adds Alpaca paper/live | ○ | ◐ | ● | ○ | ● | ◐ (via FinRL-Trading) | ◐ | Fully local (no LLM needed) | Mature as a research library; RL-on-prices results are notoriously fragile |
| 13 | [microsoft/qlib](https://github.com/microsoft/qlib) | 50,272 | 2026-11-04 | MIT | ML quant platform: data, factor/model zoo, backtest, portfolio. Companion [RD-Agent](https://github.com/microsoft/RD-Agent) (15,367, MIT) automates factor/model R&D with LLMs | ◐ (RD-Agent) | ● | ● | ◐ | ● | ○ | ○ | Qlib fully local; RD-Agent README: OpenAI/DeepSeek only | Most serious "own model" scaffolding in OSS. A-share-first data defaults |
| 14 | [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | 22,522 | 2026-11-13 | Apache-2.0 | Production algo engine (Python/C#), equities, options, futures, **forex**, crypto; backtest, paper, live via many brokers | ○ | ○ | ○ | ◐ | ● | ● | ● | Engine runs locally via Lean CLI (data and cloud features are commercial). No LLM layer | Mature, institutional-grade engine |
| 15 | [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 31,515 | 2026-11-14 | LGPL-3.0 | Rust-native event-driven engine; backtest-to-live parity; FX supported | ○ | ○ | ○ | ◐ | ● | ● | ● | Fully local | Production-grade; steep learning curve. HN discussion 2025-08 (208 pts) |
| 16 | [Lumiwealth/lumibot](https://github.com/Lumiwealth/lumibot) | 2,234 | 2026-11-14 | GPL-3.0 | Python framework with "AI agents that place the trade"; stocks, options, futures, forex, crypto; backtest/paper/live (Alpaca, etc.) | ◐ | ○ | ○ | ◐ | ● | ● | ● | README: Claude mentioned, no Ollama; GPL-3.0 | Commercial vendor behind it; reasonably active |
| 17 | [pst-group/pysystemtrade](https://github.com/pst-group/pysystemtrade) (Carver) | 3,628 | 2026-11-02 | GPL-3.0 | Rob Carver's systematic futures framework: vol targeting, forecast combination, IB live trading | ○ | ◐ (rule-based forecasts) | ○ | ● | ● | ◐ | ● | Fully local | The sober reference design. No LLM |
| 18 | [Fincept-Corporation/FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) | 33,790 | 2026-11-13 | AGPL-3.0 | Desktop finance terminal, 37 agents (README), BYO key | ● | ◐ | ○ | ◐ | ◐ | ○ | ○ | BYO key: Anthropic, Ollama, others | Unverified depth |
| 19 | [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) | 47,771 | **2026-04-13** | MIT | Foundation model for candlestick (K-line) sequences | ○ | ● | ◐ | ○ | ○ | ○ | ○ | Open weights, local. Stale 7 months despite stars | Forecasting-layer candidate (covered by another track) |
| 20 | [google-research/timesfm](https://github.com/google-research/timesfm) / [amazon-science/chronos-forecasting](https://github.com/amazon-science/chronos-forecasting) | 35,470 / 6,301 | 2026-11-13 / 2026-10-05 | Apache-2.0 | General time-series foundation models | ○ | ● | ○ | ○ | ○ | ○ | ○ | Local | Forecasting layer (other track) |
| 21 | [OpenBB](https://github.com/openbq-org/OpenBB) | 75,406 | 2026-11-14 | NOASSERTION | Data platform for analysts and AI agents. **Note: API redirected `OpenBB-finance/OpenBB` to `openbq-org/OpenBB`; verify the canonical repo before cloning** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | Local data layer | Widely used; verify owner |
| 22 | [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | 56,864 | 2026-11-12 | GPL-3.0 | Crypto bot with backtest, hyperopt, dry-run, live | ○ | ◐ (FreqAI per my memory, unverified) | ◐ | ◐ | ● | ● | ● | Fully local | Mature but crypto-only. Not FX/metals/stocks |
| 23 | [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot) | 6,941 | 2026-11-02 | GPL-3.0 | Crypto bot with grid/DCA/AI | ◐ | ○ | ○ | ◐ | ● | ● | ● | Local | Crypto-only |
| 24 | [wquguru/nof0](https://github.com/wquguru/nof0) | 2,754 | 2025-12-07 | none | Open reproduction of nof1 Alpha Arena (Hyperliquid) | ● | ○ | ○ | ○ | ○ | ○ | ● | Unknown | Stale 11 months; no license |
| 25 | [HammerGPT/Hyper-Alpha-Arena](https://github.com/HammerGPT/Hyper-Alpha-Arena) | 1,200 | 2026-11-03 | Apache-2.0 | AI trading platform for Hyperliquid/Binance futures | ● | ○ | ○ | ◐ | ○ | ○ | ● | Unverified | Crypto perps |
| 26 | [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server) | 1,082 | 2026-11-13 | MIT | Official broker MCP server: trade stocks/ETFs/options/crypto, data | ○ | ○ | ○ | ○ | ○ | ● | ● | Local server; works with Claude | Official, small, useful building block |
| 27 | [The-FinAI/Agent_Market_Arena](https://github.com/The-FinAI/Agent_Market_Arena) (9) and [ulab-uiuc/live-trade-bench](https://github.com/ulab-uiuc/live-trade-bench) (168) | 9 / 168 | 2026-10-08 / 2026-02-17 | MIT / NOASSERTION | Live multi-market benchmarks for LLM agents (arXiv 2510.11695) | ● | ○ | ○ | ○ | ◐ | ● | ○ | Unverified | Academic benchmarks; useful as evaluation designs |

Other lists and hubs (verified metadata):
- [wilsonfreitas/awesome-quant](https://github.com/wilsonfreitas/awesome-quant): 30,627 stars, pushed 2026-11-14, no license.
- [paperswithbacktest/awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading): 15,347 stars, pushed 2026-09-28.
- [georgezouq/awesome-ai-in-finance](https://github.com/georgezouq/awesome-ai-in-finance): 6,752 stars, CC0, pushed 2026-11-12.
- [LLMQuant/awesome-trading-agents](https://github.com/LLMQuant/awesome-trading-agents): 998 stars, CC0, pushed 2026-08-13.
- Engines/libs (not "end-to-end" but you will reuse them): [vectorbt](https://github.com/polakowo/vectorbt) 9,842 stars; [backtesting.py](https://github.com/kernc/backtesting.py) 9,237 (AGPL); [backtrader](https://github.com/mementum/backtrader) 23,737 (last push 2024-08-19, effectively dormant); zipline (Quantopian, 20,237, last push 2024-02-13, dormant); [skfolio](https://github.com/skfolio/skfolio) 2,637; [Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) 4,607; [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) 6,166; [quantstats](https://github.com/ranaroussi/quantstats) 7,865; [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest) 5,084; [stefan-jansen/machine-learning-for-trading](https://github.com/stefan-jansen/machine-learning-for-trading) 21,810 (3rd ed.); [vnpy](https://github.com/vnpy/vnpy) 46,370; [ccxt](https://github.com/ccxt/ccxt) 44,878; [yfinance](https://github.com/ranaroussi/yfinance) 25,916.

### 2.2 Commercial and hosted offerings (thin verification)

I did not deeply verify any commercial product. What I can say from sources I fetched:
- **Nof1** describes itself as an AI research lab "building new models for financial markets" (nof1.ai, fetched). Alpha Arena is archived/watch-only per a competitor's blog (see section 3).
- **QuantConnect** (cloud on top of Lean), **Alpaca** (broker + MCP), **BingX AI Arena** (copy a model's trades with real leverage), **RockAlpha / RockFlow Auto Copy**, **Rallies.ai**, **TradeRank**, **Strategy Arena** (lets you connect a local model via an Ollama/OpenAI-compatible endpoint): all appear in TradeRank's comparison post (vendor blog, one of the five listed is the author's own product).
- **Robinhood** reportedly introduced AI-agent trading services (mentioned in a Substack post; no primary source seen). Unverified.
- SEC enforcement shows what happens to commercial overclaiming: Delphia ($225k) and Global Predictions ($175k) settled the first "AI washing" cases on 2024-03-18 (SEC press release 2024-36, search-result summary).

### 2.3 Which are closest to the user's vision, and what is missing from all of them

User plan layers: (1) LLM agents with news/web tools, (2) market data, (3) time-series forecasting, (4) own encoder+classifier on a "profitability index" trained progressively, (5) risk/asset management, (6) backtest + paper + real-money.

Closest in spirit:
- **Vibe-Trading** for (1), (5), (6) in one place, with Claude and Ollama support and an MT5 broker profile (FX/metals/CFDs).
- **TradingAgents** for (1) with the best multi-provider LLM abstraction (including Ollama and Claude).
- **Qlib** for (3)/(4) scaffolding (data -> model zoo -> backtest) without LLMs.
- **Lean or Nautilus or pysystemtrade** for the (5)/(6) engine, with real broker adapters and sane risk primitives.
- **LangAlpha** for a Claude-first, locally runnable research front end.

Missing from all (based on README review, not code audit):
1. **Point-in-time, leak-safe evaluation for LLM insights.** None enforce per-model knowledge-cutoff gating or store "what the agent saw at decision time" with immutable timestamps. The Alpha Illusion paper and Look-Ahead-Bench say this is the central failure mode.
2. **Insight -> outcome labeling loop.** None treat each LLM insight as a timestamped, falsifiable prediction that later gets labeled by realized, cost-adjusted outcomes, which is exactly the training-data engine your "profitability index" needs.
3. **A trained "profitability index" model fed by LLM-extracted features** with progressive/online training and calibration. Qlib comes nearest, but without LLM features.
4. **Risk layer that the LLM cannot override.** Vibe-Trading has mandates, exposure limits and a kill switch; pysystemtrade has real vol-targeting. Most agent repos let the LLM size and place trades.
5. **Cost-aware net reporting by default** (spread, slippage, funding, financing, commission), per the Alpha Illusion protocols.
6. **First-class FX/metals** with realistic spread/swap modeling and local-first operation. Vibe-Trading mentions spread/swap for Yahoo `=X` pairs in its changelog; coverage depth unverified.
7. **Paper -> live promotion gates** (minimum live-paper duration, statistical thresholds, drawdown tripwires). Not seen in any README.
8. **Apple-Silicon/MLX-native path.** Everything assumes Ollama or cloud APIs.

---

## 3. Live LLM-trading experiments and leaderboards

### 3.1 nof1 Alpha Arena

**Season 1 (crypto perps on Hyperliquid)**, 2025-10-17 to 2025-11-03. Six models with $10,000 each: Qwen3 Max, DeepSeek Chat V3.1, Claude Sonnet 4.5, Grok 4, Gemini 2.5 Pro, GPT-5. Same prompts, real money, all outputs public.
- Final (consistent across Protos dollar P&L and iWeaver percentages): Qwen3 Max +22.3% (+$2,232), DeepSeek +4.89% (+$489), Claude Sonnet 4.5 -30.81%, Grok 4 -45.3%, Gemini 2.5 Pro -56.71%, GPT-5 -62.66%. Four of six lost money. Win rates all 25-30%. Sources: [Protos](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/), [iWeaver](https://iweaver.ai/blog/alpha-arena-ai-trading-season-1-results) (iWeaver is a vendor blog, no dated snapshot).
- **Rankings reversed during the contest.** Decrypt on 2025-10-20 reported Grok, DeepSeek and Claude each up more than 25%, GPT-5 and Gemini down more than 28% ([Decrypt](https://decrypt.co/345006/ai-crypto-trading-showdown-deepseek-grok-winning-gemini-implodes)). Two weeks later Claude and Grok were deeply negative. The lesson: a two-week leaderboard is mostly path noise.
- Nof1 said P&L was "dominated by trading costs in early runs" (agents overtraded; fees erased tiny gains). Qwen paid $1,654 in fees, Gemini $1,331 (Protos). Founder Jay Azhang said LLMs do not handle numerical time series well and models showed persistent "personalities" (Claude rarely shorted; Grok/GPT/Gemini shorted more) (Protos).
- iWeaver says Qwen made roughly 43 trades (<3/day). Briefs later cited a different prompt in which Qwen made 1,418 trades vs Grok 4.20's 158, so trade count alone is not an explanation.
- Caveat on interpretation: tiny sample, one regime, leveraged crypto perps. The result says almost nothing about stocks, FX or metals.

**Season 1.5 (US equities)**, roughly late Nov to 2025-12-03 (dates differ across sources). Eight models, four two-week "competitions" (baseline with news/memory, "Monk Mode" capital preservation, situational awareness, max leverage).
- Winner: a "mystery model" later revealed as Grok 4.20, about +12% on average per a tweet relayed by [Forklog](https://forklog.com/en/news/ai-model-grok-4-2-triumphs-in-trading-tournament); GPT-5.1 second, Gemini 3 third. The averaging method is not explained in the article.
- [Briefs Finance, 2026-11-07](https://www.briefs.co/news/public-ai-trading-contests-largely-lose-money-and-raise-new/) (secondhand): combined portfolio fell about one third; only 6 of 32 individual results finished positive.
- [Flat Circle](https://blog.flatcircle.ai/p/ai-trading-arenas) calls out good design (a trading plan fed back into later calls reduces random flips) and says all models eventually lost money; Forklog said only Grok 4.2 was profitable as of 2025-12-08. These conflict on details; treat as secondhand.

**Season 2:** I found no public Season 2. A competitor's post dated 2026-11-12 (TradeRank, vendor) says no public Alpha Arena season is running and the site still shows Season 1.5 ended 2025-12-03 ([TradeRank](https://www.traderank.ai/blog/alpha-arena-alternatives-2026)). Briefs says Nof1 plans a second season with web search, longer reasoning, more data sources and multi-step actions. nof1.ai/leaderboard returned 404 and alphaarena.ai returned 429 to my fetcher; I could not view the official leaderboard.

### 3.2 Other live or public arenas (mostly via Flat Circle's survey, 2026-05; secondhand)

| Arena | Setup | Reported outcome (as of dates cited) | Takeaway |
|---|---|---|---|
| Rallies.ai AI Arena | Long-only, $100k each, US stocks | Early Jan 2026: DeepSeek-v3 about +4.6% over one month ([OneDayAdvisor](https://www.onedayadvisor.com/2026/01/AI-stock-trading.html)); May 2026: GPT leading, agents generally profitable | Bull market flatters long-only; Flat Circle: market factors likely explain most gains |
| TradeRank | Crypto paper arena, 9 premium models | 2026-05-04: 2 of 9 positive; MiniMax M2.7 +1.02%, Claude Opus 4.7 -3.70% | Vendor-run, short, paper |
| Prediction Arena (Kalshi) | 6 frontier models, tools | Most lost money after concentrated bets; winners betting on near-1c or >90c contracts | Effectively selling volatility |
| okbet (Polymarket) | 5 models same research doc | GPT-5.1 +$11, only winner | Too thin to conclude |
| Nathan Smith account | ChatGPT Deep Research weekly, small-cap healthcare, 6 months | -17% | One position -83% after trial failure; sizing problem |
| Flat Circle's own arena | Paper-trading earnings, 4Q24 | o1 and Grok-2 best, Claude 3.5 Sonnet worst; pricier models better | Results worsened in later periods |
| Aster humans vs AI | Crypto, $150k prize pool | AIs beat humans on average, but 9 of top 10 traders were human | Humans did not risk own capital |
| Strategy Arena | 75 public strategies, virtual | Allows connecting a local model via Ollama endpoint | Useful for local-model testing |

Flat Circle's bottom line (via Briefs, secondhand): across 11 arenas every arena had at least one winning model, but only two had a profitable median model. "Limited evidence of LLMs beating the market with any scale or statistical significance" is Flat Circle's own assessment.

### 3.3 Academic live/benchmarks
- **StockBench** (arXiv [2510.02209](https://arxiv.org/abs/2510.02209), Tsinghua/BUPT, v1 2025-10-02, v2 2026-03-02): daily buy/sell/hold on prices, fundamentals and news over 82 trading days (2025-03-03 to 2025-06-30). Most models fail to beat equal-weight buy-and-hold; strong static finance-QA scores do not predict trading performance. Models included GPT-5, Claude-4 and open-weight Qwen3, Kimi-K2, GLM-4.5 (per hyper.ai, secondhand; I did not read per-model numbers).
- **Agent Market Arena** (arXiv [2510.11695](https://arxiv.org/abs/2510.11695), 17 authors incl. Lopez-Lira): live crypto and stock benchmark. Finding: agent architecture shapes outcomes more than the backbone LLM ("model backbones contribute less to outcome variation"). Backbones tested were GPT-4o, GPT-4.1, Claude-3.5-haiku, Claude-sonnet-4, Gemini-2.0-flash. This is mildly supportive of "cheap/local backbone + good scaffolding," but it is one paper with older models.
- **Look-Ahead-Bench** (arXiv [2601.13770](https://arxiv.org/abs/2601.13770), Jan 2026): standard LLMs (Llama 3.1 8B/70B and DeepSeek 3.2 tested) show significant look-ahead bias via alpha decay; point-in-time models generalize better (secondhand summary).

### 3.4 The Alpha Illusion (important for architecture)
arXiv [2605.16895](https://www.alphaxiv.org/abs/2605.16895) (2026-05-16, position paper): reported alpha from end-to-end LLM trading agents should not be treated as deployment evidence unless it survives temporal-integrity, friction, counterfactual-robustness and statistics checks. The authors re-ran TradingAgents and QuantAgent over 2025-2026 (after model cutoffs) with costs; for TradingAgents the Sharpe fell from 0.43 to 0.22 net of costs. They propose six tiered reporting protocols (P1-P6) and recommend a modular design: LLM extracts information; independent quant models forecast; separate modules do calibration, risk, sizing and execution. I saw only the abstract and secondary summaries (alphaXiv, Harbourfront Quant). This matches the user's planned architecture.

### 3.5 Lessons across experiments
1. Overtrading and costs eat LLM agents (Nof1 on fees; Alpha Illusion on gross-vs-net).
2. Results are regime/market-beta dominated; long-only arenas in rising markets look good.
3. Short windows plus few instruments gives no statistical power. Flat Circle credits Alpha Arena's four sub-arenas for adding some.
4. Models have stable behavioral biases (long/short tilt, leverage appetite). These are hidden factor exposures, and your system should measure them.
5. Leaderboard rank is unstable (Oct 20 vs Nov 3 reversal).
6. Backtests of 2026 LLMs on pre-2026 data are contaminated; live/forward evaluation is the only clean test (Briefs/Flat Circle).
7. Structure beats raw intelligence: constrained tasks with curated data show more promise (Briefs, Intelligent Alpha benchmark; secondhand).

---

## 4. Per-platform findings

### 4.1 Reddit (r/algotrading, r/quant, r/LocalLLaMA, etc.)
**What I could access: nothing directly.**
- `www.reddit.com/.../top.json` and search JSON returned HTTP 403 to my script.
- `old.reddit.com` returned a redirect (302); WebFetch said it is unable to fetch from old.reddit.com.
- WebSearch's `allowed_domains: ["reddit.com"]` is rejected (domain not accessible to the crawler).
- I stopped there. I did not try mirror sites, RSS or archive APIs to get around the block; the permission layer flagged that as unauthorized access and I did not push further.
- What I have is **secondhand**: ordinary web-search results that summarized or linked to Reddit threads, and sometimes to third-party mirrors I did not open. Themes from those summaries (unverified at the thread level): skepticism that LLMs belong in the trading loop ("overkill", "too slow"), a view that LLMs help only when supervised, viral anecdotes of tiny-sample wins (e.g., a four-week 23.8% microcap result and an 18-trade "100% win rate"), and LSTM+LLM hybrid pipelines tested for about a month. I cannot attribute any specific claim to a specific user or confirm the posts exist.
- **r/LocalLLaMA on finance:** I found nothing verifiable. The one LocalLLaMA hit surfaced was a general Qwen3-30B-A3B appreciation thread (April 2025) via a mirror, not finance-specific.
- **Action for the user:** read r/algotrading, r/quant, r/LocalLLaMA yourself or use a logged-in browser session. Treat anything I say about Reddit as a lead, not a finding.

### 4.2 Hacker News (Algolia API: fully accessible)
Queried the Algolia API directly (stories with more than 40 points) and read comment trees.
- [Multi-Agents LLM Financial Trading Framework (TradingAgents), 2026-09-08, 120 pts, 81 comments](https://news.ycombinator.com/item?id=49605822). Paraphrased themes:
  - A commenter who says they worked in hedge funds argued that role-splitting identical LLM agents misses how funds actually work and that scraping Reddit sentiment is weak.
  - "If this worked it wouldn't be open source." Another commenter reports running their own LLM experiment that "lost a bit of money."
  - A commenter claims a one-hour code review found concrete issues (double-weighted Yahoo News input, a prompt that primes bullishness on one stock, a memory-parsing bug that can hallucinate memories on truncated outputs). This is a single anecdote I could not verify against the code.
  - Repeated requests for a performance section or backtest. Debate over whether multi-agent beats a single agent with a good harness.
  - Several commenters predict someone from r/wallstreetbets will lose real money with it.
- [Ask HN: Anyone making money through algorithmic trading? (2018, 389 pts, 245 comments)](https://news.ycombinator.com/item?id=16922538). Mix of crypto arbitrage hobbyists ("not enough juice in it"), one commenter who says they lost about $100k over two years, and a survivorship-bias comment (ask enough people about coin flips and some say yes). Dated, but the dynamics are timeless.
- [Show HN: Watch 3 AIs compete in real-time stock trading (2024-12-31, 270 pts)](https://news.ycombinator.com/item?id=42559744) and [NautilusTrader (2025-08-06, 208 pts)](https://news.ycombinator.com/item?id=44810552), [TradeExpert MoE LLM trading framework (2025-06, 114 pts)](https://news.ycombinator.com/item?id=44157378), [Misalignment and deception by an autonomous stock trading LLM agent (2023-11, 91 pts)](https://news.ycombinator.com/item?id=38353880). I did not read these comment trees in full.
- Local-LLM-for-finance on HN: the only relevant hit above the 40-point threshold was Show HN: Ekselio, "local first" finance workflows (2026-09-25, 43 pts). No substantive local-LLM-for-trading thread found.

### 4.3 YouTube (search-result metadata accessible; transcripts not read)
I could read search results (title, channel, views, age) but not transcripts, so I can only report **titles and what the title claims**, not what the video shows. Views and ages as seen on 2026-11-14.
- "I Gave the Grok Bot AI Trading Bot $10,000 for 22 Hours..." - Trading with DaviddTech, 255k views, 2 months ago. Same brand name appears as a GitHub repo (DaviddTech/ai-trading-agent, 97 stars) selling an agent skill pack; I did not verify they are the same person.
- "I tried coding a LLM Crypto Trading Bot (to retire early $$$)" - Nicholas Renotte, 149k views, 1 year ago.
- "Do Trading Bots Really Work? I Gave a Trading Bot $55000 to Trade" - ResponsibleForexTrading, 182k views, 2 years ago.
- "MASTER AI Trading Bots in 61 Minutes (Claude + TradingView)" - Mind Math Money, 75k views, 6 days ago; "How To Actually Build an AI Trading Bot With Claude (3 Hour Course)" - AI Pathways, 81k views, 6 days ago. Claude-based trading tutorials are trending right now.
- Local-LLM trading: "Someone open-sourced a hedge fund - I ran it locally on Qwen3 with Ollama" - Prompt Engineer 48, 35k views, 6 months ago (almost certainly virattt/ai-hedge-fund; unverified); "Run This Multi Agent AI Trading System Locally with GPT, Claude, or Ollama" - The Local Lab, 9.6k views, 5 months ago; "I Built an AI Stock Analyst That Runs 100% Locally (Python + Ollama)" - The Curious Architect, 521 views, 4 months ago. These show demand and hobby-level setups; titles say nothing about profitability.
- Alpha Arena explainer videos (a dozen small channels, 650 to 6.6k views, about a year old).
- Quant-skeptic/educational: Quantpedia "Which Retail Algo Trading Strategies Actually Work?" (1.1k views), Roman Paolucci "Quant Trader on Retail vs. Institutional Trading" (53k), Hudson River Trading recruiting talk (82k), Coding Jesus "3 things day traders refuse to understand about quant trading" (77k).
- Pattern: the highest-view "AI bot" videos are short-horizon "I gave a bot $X" stunts or tutorials. Reading titles alone, none are long-horizon audited track records. Treat the format as entertainment/lead-gen (unverified motives).

### 4.4 X/Twitter
**Not accessible.** x.com/jay_azhang returned HTTP 402 to WebFetch. The only X content I have is the Season 1.5 winner announcement as relayed by Forklog (a tweet dated 2025-12-05 from the Nof1 founder). I could not scan quant accounts or threads. A logged-in session or API access is required.

### 4.5 Instagram and TikTok
**Not crawlable.** The TikTok tag page returned only a shell page (no videos). I did not attempt Instagram. A first search aimed at finfluencer scam coverage was blocked by the permission layer, so I reran with a regulator-oriented query. Regulator and press material about finfluencers (secondhand search summaries, not primary documents):
- IOSCO (2023-03) report on finfluencers cites a Dutch study of 150 finfluencers finding few posted neutrally and some promoted risky products.
- ESMA issued a statement on investment recommendations on social media (2021-12).
- FCA: October 2025 report says more than 90,000 investors lost about £75M over four years at one firm promoted by finfluencers; 38 alerts on finfluencer accounts ([Finance Magnates](https://www.financemagnates.com/forex/fca-reports-75m-cfd-loss-for-90k-retail-investors-at-one-firm-promoted-by-finfluencers/)).
- ASIC: June 2025 warning notices to 18 finfluencers over high-risk product promotion.
- SEC: charges against eight individuals in a $100M scheme using Twitter and Discord to manipulate stocks.
What the content itself looks like (specific posts, claims, engagement): **I could not observe it.**

### 4.6 Discord and Telegram
**Not accessible** (invite-gated; no public index tried). I only noticed that nofx links a Telegram community and HKUDS projects link Feishu/WeChat groups. I cannot report community sentiment. Prudence: crypto/AI-bot Telegram and Discord groups are a primary distribution channel for signal sellers (see CFTC and SEC items in section 6), so a lack of access here is not a loss.

### 4.7 Forums: MQL5, Elite Trader, Forex Factory, Quantopian successors
- **MQL5 forum:** accessible. [Thread "Is there a profitable EA on mql or are they all scams?" (2021)](https://www.mql5.com/en/forum/364384) summarized: a moderator notes the Market guarantees nothing and advises buying only from sellers you know; posters say marketing dominates, honest sellers show realistic drawdowns and lose to implausibly smooth curves, OHLC vs real-tick modeling changes results sharply, and a live real-money signal is better evidence than a backtest. MQL5 blogs on "How Developers Fake Backtests" and martingale/grid detection exist ([example](https://www.mql5.com/en/blogs/post/774651)); many are written by EA sellers, so read with that bias.
- **Elite Trader:** homepage returned 200 to curl, but the forum URL I tried returned 404 via WebFetch; I did not get thread content.
- **Forex Factory:** returned 403 to automated requests. Not accessed.
- **Quantopian successors:** Quantopian's code survives as zipline (dormant, last push 2024-02-13); the community moved largely to QuantConnect forums. QuantConnect's site is reachable; I did not read its forum. The Quantopian cohort study of 888 algorithms is the best public evidence on retail-style algo overfitting (section 5).
- **Quantocracy** (curated quant-blog aggregator): accessible. Its 2026-11-11 front page included posts with "claimed vs measured" framing, for example "MA 9/21 + 200 MA on Gold: 58% Claimed, 42.3% Measured" (Nullius Research) and "Bitcoin Abnormal Day Momentum Backtest: 91% Became 41%". That is a healthy sign: verification culture exists in the quant-blog ecosystem.

### 4.8 Recurring themes across what I could actually read (HN, forums, papers, YouTube titles, press)
What seems to work (consensus across sources, not proven):
- Slow, simple, diversified, cost-aware systematic strategies with strict risk control; verification via live small-size forward test.
- LLMs as research assistants and information extractors, not as autonomous portfolio managers.
- Measuring claimed vs. measured performance; modeling costs; testing after training cutoff.

What does not:
- Autonomous LLM traders with leverage and short horizons; martingale/grid EAs with smooth equity curves; backtest-only evidence; "agent personas" as a source of alpha (HN skepticism; AMA suggests backbone matters less than scaffolding).

Tools people name: freqtrade, Lean/QuantConnect, Nautilus, backtrader (dormant), vectorbt, Qlib, pysystemtrade, Alpaca, IBKR, MT5/MQL5.

Common mistakes: overfitting many configs (Bailey/Borwein/Lopez de Prado), ignoring costs, look-ahead leakage (including LLM memorization), too-short evaluation windows, survivorship bias in "anyone making money?" threads, trading leverage you do not understand.

---

## 5. Retail outcome evidence

### 5.1 Broker/regulator disclosures (fetched 2026-11-14 from live pages)

| Provider | Disclosed % of retail accounts losing money | Page / note |
|---|---|---|
| IG (UK) | 70% | ig.com/uk footer, fetched. Period not shown in the extract |
| CMC Markets (UK) | 69% | cmcmarkets.com/en-gb/trading-platforms, fetched |
| eToro | 55% | etoro.com general risk disclosure, fetched |
| Pepperstone | 80% | pepperstone.com/en, fetched |
| Plus500 | not retrieved (HTTP 403) | BrokerRank reports 82% (secondhand, unverified) |
| ESMA benchmark | 74-89% | ESMA product-intervention measures (2018) and renewals; 74-89% wording carried in later notices (search-result summary of ESMA documents) |
| FCA 2017 | about 78% of active retail CFD accounts loss-making (secondhand) | FCA consultation CP18/38 |

Notes: the percentage counts accounts, not money. Rules require providers to publish a provider-specific percentage computed over a trailing 12 months and updated quarterly (ESMA measures, secondhand). Secondary compilations disagree with each other and with the pages I fetched (for example one lists eToro at 79%), so use broker pages directly and date-stamp them.

- **Finance Magnates / iSAM Securities Radar** (data vendor to brokers, 12 months to mid-Aug 2026): 79.5% of retail clients ended in loss, 20.5% in profit; the top 1% of winning accounts captured 66.5% of winnings and the top 5% captured 85.5%; 94.6% of client volume was B-booked; **XAUUSD was 79.3% of broker volume and 62% of broker P&L**; 9.6% of clients were still profitable one second after a trade. Sample size not stated. Source: [Finance Magnates](https://www.financemagnates.com/forex/the-winning-few-top-1-of-retail-traders-cause-two-thirds-of-broker-losses/). Implication for metals: gold CFD is the heart of retail flow, and a few latency-advantaged accounts take much of the profit.
- Polish regulator KNF survey (secondhand, [Finance Magnates](https://www.financemagnates.com/forex/brokers/knf-survey-polish-forex-market-shows-roulette-table-concept-80-lose-money)): 80% of profitable traders lose in the long run (per search summary).
- City, University of London study of almost 100,000 retail FX traders over 2.5 years: no learning by doing; average performance slightly worsens with experience (secondhand, [Bayes knowledge page](https://www.bayes.citystgeorges.ac.uk/faculties-and-research/research/bayes-knowledge/2017/november/what-do-retail-fx-traders-learn)).

### 5.2 Academic day-trader evidence
- **Chague, De-Losso, Giovannetti, "Day Trading for a Living?"** (SSRN 3423101). Brazilian equity-index futures day traders who started 2013-2015: 97% of those who persisted more than 300 days lost money; only about 1.1% earned more than the Brazilian minimum wage and about 0.5% more than a bank teller's starting salary; no evidence of learning. 19,646 starters, only about 7.9% persisted past 300 sessions (CXO Advisory summary). Caveats: Brazil, futures, no taxes/course costs. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101) / [CXO](https://www.cxoadvisory.com/investing-expertise/day-trading-a-bust/).
- **Barber, Lee, Liu, Odean (Taiwan 1992-2006)**, later "Learning, Fast or Slow" (RAPS 2020): aggregate day-trader performance is negative; 74% of day-trading volume is generated by traders with a history of losses; the working paper reports about 1,000 of roughly 360,000 annual day traders predictably outperform (about 0.3%). I did not confirm the often-quoted "97%" in this paper (secondhand). [Berkeley PDF](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/day%20trading%20and%20learning%20110217.pdf).
- **Quantopian cohort study** (Wiecki, Campbell, Lent, Stauth; SSRN 2745220): 888 algorithms after cleaning from 7,152. In-sample Sharpe explained only about 1-2% of out-of-sample behavior (R-squared 0.01-0.02) per a CXO summary I could not check against the PDF; annualized volatility and max drawdown carried over much better. [Quantpedia summary](https://quantpedia.com/quantopians-academic-paper-about-in-vs-out-of-sample-performance-of-trading-alg/).
- **McLean and Pontiff (JoF 2016)**: across 97 published return predictors, returns are 26% lower out-of-sample and 58% lower post-publication.
- **Jensen, Kelly, Pedersen (JoF 2023, NBER w28432)**: using a Bayesian model and 153 factors in 93 countries, most factors replicate (reported replication rates roughly 83-85% depending on the test; secondary summaries differ on the exact figure).
- **Bailey, Borwein, Lopez de Prado, Zhu**: the more configurations tried, the more likely a backtest is overfit; they derive a minimum backtest length bound (formula garbled in my snippets; read the paper). [Notices of the AMS version](https://scholarworks.wmich.edu/math_pubs/40/).

### 5.3 Prop-firm pass rates (low-quality evidence)
No audited industry data. Estimates cluster around 10-20% passing a challenge and about 7% ever being paid. Firm-published examples: Topstep reports 16.8% of Trading Combines completed in 2025; E8 Markets 17.7% evaluation pass rate; HyroTrader dashboard 13.49% (one-step) and 8.70% (two-step); one small firm's trial reported 2.81% of 877 traders. Sources are mostly vendors with a stake. See [Fortunly](https://fortunly.com/statistics/prop-firm-challenge-pass-rate-statistics/) and [Track360](https://track360.io/blog/prop-trading-industry-statistics-2026) (secondhand). Note: challenge fees are the business model, so pass-rate economics are not neutral.

### 5.4 What evidence says about retail algo trading specifically
- I found **no rigorous study of retail algorithmic or EA performance** (my last search explicitly turned up none). The closest proxies are the Quantopian cohort study (in-sample metrics are weak predictors out-of-sample) and the MQL5 forum consensus (backtests of marketplace EAs are unreliable, martingale/grid dominates).
- Algorithmic automation removes emotional errors but not the three big drags: costs, overfitting, and lack of edge.
- Honest read: base rate for "solo builder produces a durable positive-expectancy automated strategy" is low. It is survivable only with a risk framework that caps losses while you find out.

---

## 6. Scams and traps checklist

**Official red flags (CFTC advisory, 2024-01-25, fetched):** guaranteed or very high returns (examples cited: "tens of thousands of percent", "100 percent win rate"); claims AI can forecast markets; low entry barrier plus referral/affiliate bonuses; fake performance on demo accounts; promotion by influencers or strangers; Ponzi-like payouts. Advice: check domain age (ICANN lookup), reverse-image-search personnel, count fees and subscriptions, report to CFTC and the FBI. A case cited: a commodity pool promising 10%+ monthly via a "proprietary trading algorithm"; one source says the operator was ordered to pay over $3.4B (secondhand). FINRA issued a similar AI-fraud advisory the same day (secondhand). [CFTC advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html).

**Regulatory enforcement on "AI" claims:** SEC "AI washing" settlements (Delphia $225k, Global Predictions $175k, 2024-03-18). [SEC release 2024-36](https://www.sec.gov/newsroom/press-releases/2024-36).

**Checklist**
1. **Track record**: live, broker-verified, with cost-inclusive statements, multi-year; not backtests, demo balances, or screenshots. MQL5 forum consensus: a live signal helps but does not prove profitability.
2. **Equity curve shape**: unnaturally smooth curve + high win rate = suspect martingale/grid (MQL5 posts). Check lot-size progression.
3. **Backtest hygiene**: excluded dates, optimized parameters (one MQL5 blog reports parameter optimization turning a $10k backtest into $108k on a gold EA), OHLC vs real-tick modeling, no spreads/swap.
4. **Seller incentives**: the product price, subscription, "VIP signals", affiliate links, broker IB rebates. Ask who profits if you lose.
5. **Regulation**: broker authorized by FCA/ASIC/CySEC/SEC-FINRA-NFA; check the register yourself. Unregulated offshore brokers are a recurring trap (secondhand).
6. **Copy-trading/AI-arena copy features**: BingX AI Arena copy trades run with real leverage, liquidation and funding risk (TradeRank post, secondhand).
7. **Finfluencers**: FCA says one firm promoted by finfluencers lost 90k+ retail investors about £75M (secondhand).
8. **Onboarding red flags in code/projects**: "paste this link/message into your agent to register" (AI-Trader pattern); wallets you must fund; telemetry or key exfiltration (read the code); tokens or airdrops; pay-per-call data via crypto wallets as the only data path.
9. **Real vs grift open source**: permissive license that is actually declared (several big repos show NOASSERTION or none); multi-year commit history and multiple independent contributors; open issue triage; disclaimers instead of performance claims; reproducible backtest scripts with costs; no "guaranteed" language; maintainers who publish failures (Quantocracy-style "claimed vs measured"). Stars: both TradingAgents (122k) and daily_stock_analysis (72k) have enormous counts for a research repo; I could not verify organic vs manufactured. Do not use stars as a proxy.
10. **LLM-specific**: any LLM-trading performance claim must state the model's knowledge cutoff and the test window relative to it. Without that, discount it.

---

## 7. Realistic edge for a solo builder (hypotheses with sources)

All of the below are hypotheses, not validated for your setup. Sources are named; "unverified" means I did not fetch the primary text.

**Where small players plausibly have a chance**
1. **Slow, diversified, low-turnover systematic strategies** (trend, carry, value/momentum) across futures/FX/metals/equity indices, risk-targeted. Evidence: Hurst, Ooi, Pedersen, *A Century of Evidence on Trend-Following Investing* (JPM 2017; extends to 1880; I did not retrieve the Sharpe figures). Caveats: Carver argues retail capital limits proper diversification in futures (a summary says roughly $100-250k needed; unverified against his book), so a small account is better served by ETFs or micro-contracts and by watching costs. CFD financing and spread costs can swamp slow strategies.
2. **Risk and volatility management as the dependable value-add.** Vol targeting, position-size caps, correlation-aware sizing, drawdown tripwires. This is the Carver/pysystemtrade approach (practitioner consensus; the blog is current, see reading list). It does not create alpha; it improves the odds of surviving long enough to find any.
3. **Cross-sectional equity signals with low turnover** that survived replication: Jensen-Kelly-Pedersen say most published factors replicate, but McLean-Pontiff say post-publication decay is large (58%). Small caps are where mispricing is larger but costs and capacity matter. As a solo builder with free/cheap data, open-source asset pricing datasets reduce data costs (Chen-Zimmermann open asset pricing; from memory, unverified).
4. **LLM as latency-tolerant information extractor.** Convert filings, transcripts, news into structured features (event type, scope, horizon, novelty) feeding a conventional model, then measure incremental predictive power net of costs. Alpha Illusion recommends exactly this modularity. Evidence for predictive content exists (Lopez-Lira and Tang; but their v6 abstract emphasizes immediate market reaction, which is the part latency-constrained retail cannot capture), and Glasserman and Lin show look-ahead and "distraction" effects can inflate or deflate in-sample results. Plausible niche: less-covered small/mid caps and slower post-event drift where institutions do not bother. Unverified for your execution constraints.
5. **Event/news interpretation with latency tolerance:** hold periods of days-weeks after earnings or filings (post-event drift) rather than seconds. Hypothesis only.
6. **Idiosyncratic niche knowledge** (specific commodities, regional markets, micro-structure quirks). Hard to evidence and not LLM-dependent.

**Where small players are competing with HFT/institutions and usually lose**
- Sub-minute news trading and latency arbitrage (iSAM data shows brokers actively flagging clients profitable one second after a trade).
- Intraday scalping of gold/FX CFDs against a B-book broker. Gold is 79% of broker volume in iSAM's data, i.e., the most contested retail arena.
- Crypto perps with leverage using autonomous LLMs (Alpha Arena S1 outcomes).
- Trading widely published anomalies right after publication (decay).
- Market-making and arbitrage needing colocation or capital.

**Per asset class (hypotheses)**
- Stocks: most data and replicable literature; best for cross-sectional/LLM-feature work; costs lowest via ETFs/commission-free brokers; beware earnings gaps (Nathan Smith example: one position -83%).
- FX: no cross-section to speak of; retail evidence is poor (City University study: no learning; spread cost correlates with profitability). Slow carry/momentum/value signals plausible but unproven for small accounts.
- Metals: gold dominates retail CFD flow; use as a diversifier in a slow portfolio rather than an intraday target. Futures/ETF exposure may be cheaper than CFDs.

---

## 8. Local-first stack (new section)

Constraint: Claude is the only allowed cloud LLM; everything else local on Apple Silicon. Findings are weak-to-moderate; I could not read Reddit, so no community consensus claims.

### 8.1 What exists for local models in this space
- **Project support:** TradingAgents (Ollama and any OpenAI-compatible endpoint; per-role provider mixing, e.g., managers on Claude and analysts local), Vibe-Trading (Ollama, Claude native, `claude-cli`), LangAlpha (Ollama, LM Studio, vLLM; Claude), Fincept (Ollama; Anthropic), daily_stock_analysis (Ollama; Claude). virattt/ai-hedge-fund: current README lists no Ollama. nofx: AI routed through a hosted service. Quant engines (Lean, Nautilus, pysystemtrade, Qlib, FinRL) are LLM-free and fully local.
- **Good design pattern already in TradingAgents:** a cheap "quick" model for analysts and a "deep" model for managers, each configurable independently. You can map this to local-quick plus Claude-deep.

### 8.2 Evidence on which local models are adequate for financial news extraction/summarization
- **arXiv [2512.00946](https://arxiv.org/abs/2512.00946)** (preprint): FinBERT vs DeepSeek-LLM 7B, Llama3 8B Instruct, Qwen3 8B on five financial sentiment datasets. Qwen3 8B and Llama3 8B generally beat FinBERT, including with about 5% of the training data; Qwen3 8B held up best with little fine-tuning data; Llama3 8B pulled ahead once fully fine-tuned. FinBERT degraded when fine-tuned on news/tweet datasets. Limits: only 7-8B models; no Gemma; no Claude comparison.
- **arXiv [2512.14717](https://arxiv.org/html/2512.14717v1)** ("Is GPT-OSS all you need?"): five open-weight models, run locally on 8x H100, over ten financial NLP tasks (mostly sentiment, plus QA, NER, stock-news prediction). Average accuracy: GPT-OSS-120B 66.5%, GPT-OSS-20B 65.1%, Qwen3-30B 63.6%, Qwen3-235B 62.9%, Llama4-Scout 49.3%. The paper claims GPT-OSS-20B reaches 97.9% of the 120B model's accuracy at about 83% less memory, though I flagged internal inconsistencies in its speed claims. Takeaway: even the best open model scores only mid-60s on these tasks, and a 20B model is nearly as good as far larger ones. No Claude baseline.
- **Structured event extraction:** a secondhand summary describes Llama-3.1-70B labeling 41,618 news-stock pairs with event category, impact scope and time horizon, with labels correlating with stock movement independent of sentiment ([summary](https://themodelwire.com/article/llama-extracts-multi-dimensional-financial-signals-beyond-sentiment-01KYV2340BEQDCV78D34FNFRSN)). I did not read the paper.
- **JSON/structured output (blogs, unclear methodology):** claims that Qwen3-32B and Gemma-3-27B hold above 95% field accuracy on deeply nested schemas and Qwen3-14B is within about 1.3 points of Qwen3-32B ([bestllmfor.com](https://bestllmfor.com/best/structured-data-extraction-json/)). Treat as directional. Same search noted Ollama's schema-constrained output underperformed a vLLM setup in one blog (unverified).
- **Agent-level:** Agent Market Arena found backbone matters less than agent design (older models, one paper). StockBench included open-weight Qwen3/Kimi-K2/GLM-4.5 but I did not read per-model results.
- **Not found:** any head-to-head of local models vs Claude vs GPT on financial news extraction with downstream trading P&L; any credible Reddit/HN/YouTube consensus. Gemma has no financial benchmark I could find. The YouTube titles above show people run Qwen3 + Ollama locally with TradingAgents/ai-hedge-fund-style stacks, but titles carry no accuracy data.
- **Apple Silicon throughput (secondhand community benchmarks):** Qwen3-30B-A3B in MLX on an M4 Max with 128GB runs around 40-65 tokens/s generation typical (some anecdotal reports higher), with prompt processing roughly 700-1,300 tokens/s depending on context. A 20B-class model fits comfortably in 32-64GB at 4-bit quantization (inference from sizes; my memory, unverified for your machine). Which Mac you have determines everything; I assumed Apple Silicon only.

### 8.3 Contamination caveat specific to local models
Every open model has a fixed cutoff. Look-Ahead-Bench found Llama 3.1 (8B/70B) and DeepSeek 3.2 show look-ahead bias. Rules: record each model's cutoff; backtest LLM-derived features only on data after the cutoff (or use point-in-time models); keep a live forward-test ledger; never mix pre-cutoff test windows into evaluation.

### 8.4 Pragmatic local-first architecture suggestion
1. **Bulk, high-volume, low-stakes (local):** news/filing dedup, entity and ticker linking, event-type tagging, sentiment, 1-3 sentence summaries, structured JSON feature extraction. Candidates to trial: Qwen3 8B/14B/30B-A3B, Gemma 3 27B, GPT-OSS-20B, Llama 3.x 8B; FinBERT/FinGPT-style encoders as cheap baselines.
2. **Judgment, synthesis, adversarial review (Claude):** cross-source reasoning, thesis writing, contradiction checks, and auditing the local model's labels.
3. **Quant core (local, no LLM):** forecasting, own encoder+classifier, risk, portfolio sizing, backtest engine (Lean/Nautilus/vectorbt/pysystemtrade-style primitives).
4. **Calibrate locally vs Claude on your own labeled set.** Hand-label about 300-500 headlines/filings; measure agreement with Claude and, more importantly, **incremental information coefficient net of costs** of each model's features. A cheaper extractor that is 5% worse on F1 may be equal on downstream P&L, or may not. Only measurement decides.
5. **Claude-only cloud boundary:** tool responses and prompts sent to Claude should avoid leaking portfolio details unless intended; local models for anything private.
6. **Terms check:** if you plan to run Claude via a consumer subscription login as a headless backend (as Vibe-Trading's `claude-cli` provider does), check Anthropic's usage terms; I did not verify.

---

## 9. Reading list

Blogs and aggregators (reachable on 2026-11-14 unless noted):
- Quantocracy aggregator: https://quantocracy.com/ (verified; claimed-vs-measured posts on front page)
- Rob Carver, "This Blog is Systematic": https://qoppac.blogspot.com (verified; posts on 2026-11-03 and 11-04 about portfolio optimisation with costs; his newer material also lives at blog.systematicmoney.org, which did not respond to my curl)
- Ernie Chan's blog: https://epchan.blogspot.com (reachable)
- Quantpedia: https://quantpedia.com (reachable; also the Quantopian paper summary)
- QuantStart: https://www.quantstart.com (did not respond to my check; unverified)
- AQR research library: https://www.aqr.com/Insights/Research (reachable)
- Alpha Architect: https://alphaarchitect.com (403 to my script; humans can usually read)
- CXO Advisory: https://www.cxoadvisory.com (used for summaries)
- Flat Circle on AI trading arenas: https://blog.flatcircle.ai/p/ai-trading-arenas
- Harbourfront Quant on LLM agent effectiveness: https://harbourfrontquant.substack.com/p/how-effective-are-llm-trading-agents
- MQL5 forum and blogs (EA skepticism material): https://www.mql5.com/en/forum

Books (not fetched; from my knowledge, verify editions):
- Robert Carver: *Systematic Trading* (2015), *Smart Portfolios* (2017), *Leveraged Trading* (2019), *Advanced Futures Trading Strategies* (2023). Code: https://github.com/pst-group/pysystemtrade
- Marcos Lopez de Prado: *Advances in Financial Machine Learning* (2018), *Machine Learning for Asset Managers* (2020).
- Ernie Chan: *Quantitative Trading*, *Algorithmic Trading*, *Machine Trading*.
- Stefan Jansen: *Machine Learning for Algorithmic Trading* (code: https://github.com/stefan-jansen/machine-learning-for-trading, 21.8k stars, 3rd edition).
- David Aronson: *Evidence-Based Technical Analysis*. Grinold and Kahn: *Active Portfolio Management*.

Papers cited above (all linked in sections): Bailey et al. (backtest overfitting), McLean and Pontiff, Jensen-Kelly-Pedersen, Hurst-Ooi-Pedersen, Chague et al., Barber et al., Wiecki et al., Lopez-Lira and Tang (arXiv 2304.07619), Glasserman and Lin (arXiv 2309.17322), StockBench (2510.02209), Agent Market Arena (2510.11695), Look-Ahead-Bench (2601.13770), Alpha Illusion (2605.16895), local-model sentiment studies (2512.00946, 2512.14717).

---

## 10. Open questions

1. Which Mac (chip, RAM)? It decides the local model class (8-14B vs 30B MoE vs 70B) and whether Claude vs local routing is cost- or capability-driven.
2. Does the "profitability index" target a horizon (days? weeks?) and an execution venue (stocks vs CFD vs futures)? CFD cost drag could kill slow strategies; this must be decided before data collection.
3. How will the system prove it is not leaking? Needs a per-model cutoff registry and forward-only evaluation ledger from day one.
4. What is the live-promotion rule (minimum paper months, minimum trades, drawdown tripwires, confidence thresholds)? Nobody ships one.
5. Is FX/metals in scope for LLM-driven insight at all? Evidence for LLM news edge in FX/metals is essentially absent in what I found; the literature skews to equities.
6. Reddit, X, Instagram/TikTok, Discord/Telegram were not accessible to me. Someone with logged-in access should skim r/algotrading, r/LocalLLaMA, r/quant, and X quant accounts for local-model-for-finance experience reports. That remains an unfilled gap.
7. Verify against primary sources before relying on them: the CFTC advisory date and the $3.4B figure; broker disclosure periods; FCA/ESMA numbers; Carver's capital-requirement claim; McLean-Pontiff and JKP exact numbers (I cited summaries); the HN commenter's code-review claims about TradingAgents; the Alpha Illusion's full text and reproduction code (github.com/hj1650782738/Trading).
8. Is `claude -p` / subscription-backed headless use allowed by Anthropic terms for an automated trading research app? I did not verify.
9. OpenBB's repo owner changed (OpenBB-finance to openbq-org per API redirect): confirm legitimacy before depending on it.
10. Alpha Arena Season 2: status unclear (possibly private); worth checking the official site and X periodically for any real result.
