# Project Get-Rich: Architecture v0.1

Date: 2026-11-14. Built from the research in `research/` (start with `research/00-master-report.md`, then `08`–`11` for the Sri Lanka / Binance / cTrader-MT5 / free-data updates). This is an engineering design for a personal research and trading tool, not investment, legal or tax advice.

Items marked **[own calc]** are my arithmetic from stated assumptions. Items marked **[verify]** were not confirmed against a primary source.

---

## 1. Decisions locked in

| Decision | Choice | Source |
|---|---|---|
| Location / use | Sri Lanka, personal use only | You |
| Hardware | Mac mini M4, 16 GB RAM, always-on at home (reported disk: 228 GiB, 47 GiB free) | You + track 10 |
| Data | Free sources only | You |
| Markets, v1 | Crypto (Binance) + gold/FX (cTrader first, MT5 second) | You |
| Style | Slow: daily bars, holding days to weeks | You |
| Capital, first live phase | Under $500 | You |
| Autonomy | You approve every order at first | You |
| Interface | Terminal only for now | You |
| LLM | Claude only in the cloud, about $30/month; everything else local | You |
| Agent roles | Daily briefing + event-risk flags first, then trade review, then shadow-mode signal generation | You |
| Max drawdown halt | Derived in Phase 1 and approved by you: 15% account, 2.5% daily, 20% exposure cap | You + me |
| FX/gold legal position | You will handle it. I flagged CBSL's 2019 notice and the funding limits (track 08); all live FX paths stay behind your manual approval | You |
| Builder | Strong Python/ML, 10+ hours/week | You |

---

## 2. Design principles

1. **Evidence before money.** Every layer must beat a dumb baseline under honest evaluation before it can touch live capital.
2. **The LLM is never in the order path.** Claude produces typed insights and features. Only the risk gate can approve orders.
3. **Record from day one.** All current Claude models list a June 2026 training cutoff, so only forward data you record yourself is clean evidence. The recorder starts before any cleverness.
4. **Slow and boring first.** The evidence supports slow trend and volatility-based sizing; short-horizon ML is fragile after costs (tracks 03, 11).
5. **Local-first.** Everything runs on the Mac mini except: Claude API calls, broker/exchange connections, and one optional Windows VPS gateway for MT5.
6. **Fail safe.** A crashed process, stale data, lapsed login or lost network must leave no unprotected positions: server-side stops on every order.
7. **Observe everything, from outside the trading path.** Every decision is traceable end to end, and the watchdog runs in its own process (see 4.7).

---

## 3. System overview

```
┌──────────────────────── MAC MINI M4 (home, always-on) ────────────────────────┐
│                                                                               │
│  COLLECTORS (launchd)         STORE (DuckDB + Parquet, append-only)           │
│  Binance REST/WS ─┐           bars, funding, OI, macro, COT                   │
│  Dukascopy, HistData ─┤──────► news/events (bitemporal: published_at,         │
│  FRED/ECB/Fed/BoE/BoJ ─┤        ingested_at)                                  │
│  GDELT, RSS, CFTC  ─┘                                                         │
│                                   │                                           │
│  PRE-FILTER (local, no LLM)       ▼                                           │
│  dedupe, embeddings, FinBERT score ──► candidate items                        │
│                                   │                                           │
│  CLAUDE (cloud, via API)          ▼                                           │
│  Haiku: extraction → events · Sonnet: briefing, review ──► INSIGHT LEDGER     │
│                                   │            (immutable, scored later)      │
│  FEATURES ─► BASELINES (trend, HAR vol) ─► PROFITABILITY INDEX MODEL          │
│                                   │        (PI-Net: encode→fuse→heads)        │
│                                   ▼                                           │
│                        TRADE INTENTS (typed, no orders)                       │
│ ═══════════ TRUST BOUNDARY: nothing above can reach a broker ═══════════════  │
│                                   ▼                                           │
│  OPERATOR CLI: you approve / reject each proposal                             │
│                                   ▼                                           │
│  RISK GATE (own process; hash-pinned limits file; tighten-only; offline-safe) │
│                                   ▼                                           │
│  EXECUTION ENGINE: Broker interface                                           │
│   SimBroker · BinanceBroker · CTraderBroker · Mt5Broker(→VPS)                 │
│  Monitoring · reconciliation · kill switch · heartbeat                        │
└──────────────┬───────────────────────────┬────────────────────────┬───────────┘
               ▼                           ▼                        ▼
           Binance API          cTrader Open API (native)   Windows VPS: MT5 gateway
                                                            (optional, via Tailscale)
```

**Credentials and the risk-gate question.** Track 05 wanted the risk engine to hold the broker credentials; track 06 put risk inside the framework. Resolution: only the execution process can read API keys (macOS Keychain, separate OS user), and it only accepts orders signed off by the risk gate process. Models, agents and notebooks have no key access and no network path to brokers. Binance keys are trade-only, no withdrawal permission, IP-restricted, Ed25519 [track 09].

---

## 4. Components

### 4.1 Data layer (free)

| Need | Source | Notes |
|---|---|---|
| Crypto bars, funding, OI | Binance REST API; Binance Vision bulk files for **research only** | **Licence trap (verified):** Vision terms (updated 2026-08-26) allow personal backtesting but forbid "live proprietary trading execution" (§4.2) and cover derived models (§2.4). Treat Vision as research data; build production features from REST data. The API terms were read on 2026-11-14 and do not address storing public market data either way (`docs/binance-terms-review.md`). |
| FX and metals history | Dukascopy (tick/bars), HistData | No licence text found for Dukascopy data [track 02, 10]. Validate against the execution broker's own prices before any live use. |
| Macro | FRED, ECB, Fed, BoE, BoJ, CFTC COT | Free. FRED's keyless CSV failed in one test; use an API key (free). |
| News | RSS, GDELT, central-bank feeds, exchange announcements | Check feed terms on storage and LLM use [not read]. Reddit and X are not usable. |

Storage layout: DuckDB over partitioned Parquet (`symbol/year`). Sizing [own calc, track 10]: 5 years of 1-minute bars for 20 crypto and 10 FX/metal symbols is about 3.5–6.5 GB; first-year footprint 10–15 GB. **Do not store raw trades** (aggTrades would be about 144 GB). Given 47 GiB free, budget 15 GB for data and put model artifacts on an external drive if needed.

Bitemporal news table: `published_at` (source claim) and `ingested_at` (your clock). Backtests use only `ingested_at`.

### 4.2 Agent layer (local + Claude)

- **Local on M4 16 GB (no local LLM):** a deterministic pre-filter only: dedupe, an embedding model (Qwen3-Embedding-0.6B or bge-m3) and FinBERT scoring. Embeddings also feed the PI-Net raw-text channel. This is small enough to run alongside the other services, so the memory budget (about 8 GB usable; Metal cap about 10.9 GB [track 10]) is left for model training.
- **Claude, lean budget (~$30/month):** Haiku 5.5 reads the items that survive the pre-filter and fills the structured event schema (about $1.75 per 10k articles [track 10]); Sonnet writes the daily briefing and trade review. **Cost check [own calc]:** 10k articles a day would be about $52/month at that rate, or about $26 with the Batch API's 50% discount, which leaves little room for Sonnet. So the pre-filter must cap the volume sent to Haiku, and a monthly spend cap is enforced in code. The lean estimate in track 10 is about $27/month.
- **Roles, in order:** (1) daily briefing + event-risk flags; (2) trade journal and post-mortems; (3) shadow-mode signal generation, logged and scored but never traded.
- **Insight ledger:** every insight is structured (asset, direction or risk flag, horizon, confidence, evidence ids), immutable, and scored later against realized returns. It also stores the exact model inputs and outputs for each decision so outcomes can be labelled automatically when the barriers resolve. This is the only honest evaluation of the agent layer, and it is the training data for the Claude channel of the PI-Net (see 4.3).
- **Hardening:** all web text is untrusted input. Agents emit typed JSON only; no tool access to broker keys; a fake headline must not be able to move an order (a 2026 survey found one crashed simulated markets in every run [track 01]).

### 4.3 Modelling layer: the Profitability Index model ("PI-Net")

**Intent (yours):** one model that encodes market state, forecasts and the research text, fuses them, and outputs the profitability index. It keeps improving from the data the system collects on its own. The design below does that, with each input channel earning its place by measured lift.

**Output.** Two heads on the fused representation: calibrated P(R_net > 0) and E[R_net], using triple-barrier, cost-aware labels. PI = E[R_net]; take a trade only if p > p* = (1+c)/(1+b) [track 04].

**Input channels and encoders**

| Channel | Input | Encoder | Trainable? | Backfillable? |
|---|---|---|---|---|
| Market | Daily OHLCV windows (multi-scale), volatility, funding/OI for crypto | Small GRU or TCN, or hand features | Yes (small) | Yes |
| Forecast | HAR volatility; Chronos-2 / TimesFM 2.5 quantiles normalised by volatility | Linear projection of the numeric vector | Projection only; forecasters frozen | Yes, but see leakage note below |
| Raw text | Headlines, announcements, central-bank text embedded by a frozen local model (bge-m3 or Qwen3-Embedding-0.6B), time-decayed over a window | Small trainable attention pooling | Pooling only; embedder frozen | Yes, from free archives such as GDELT [verify coverage and terms] |
| Claude research | Structured insight fields (event type, direction, horizon, magnitude, confidence, novelty, source count) plus a local embedding of the insight summary | Small MLP | Yes | **No** (forward-only, see below) |
| Context | Asset id embedding, volatility regime, scheduled-event calendar | Embeddings | Yes | Yes |

**Fusion.** Project each channel to 32–64 dimensions, add a missing-modality mask, and fuse with a gated MLP or small cross-attention. Trainable parameters stay well under 1M **[own calc, my target]**, which trains in minutes on the M4 with MPS or CPU. The text embedder stays frozen; no LoRA fine-tuning of text encoders until there are roughly 10k+ labelled events.

**The cold-start problem, stated plainly [own calc].** Daily bars give about 365 events per asset per year, so about 3.6k a year pooled over 10 assets. The Claude-insight channel has **zero history** on day one, and its judgement can't be backfilled: every Claude model's training data runs to June 2026, so its judgement on earlier periods is contaminated by memory. So:
- The Claude channel starts masked and is switched on only after enough resolved events carry insights (suggested threshold: 1,000 resolved events, to tune).
- Meanwhile the raw-text channel can be fitted on backfilled history, because a fixed embedding of a timestamped headline doesn't contain Claude's judgement.
- Train the model on **dense auxiliary targets** across all assets and days (next-day return bucket, realised-volatility bucket) alongside the sparse triple-barrier PI target. That gives the encoders far more supervision than events alone. This is a hypothesis to test, not a proven trick.
- Pool across assets with an asset embedding to increase sample size (track 04 gathered no evidence on pooled vs per-asset models).

**The improvement loop (the data flywheel)**
1. Every decision snapshot goes into the immutable ledger: all channel inputs (or a hash and pointer), model version, outputs, and the Claude insight ids.
2. An automatic outcome labeler resolves triple-barrier outcomes from collected prices and writes labels back. Your approve/reject decisions are stored as an extra signal.
3. A nightly job appends new labelled rows. Retraining is scheduled walk-forward, with early retrains triggered by ADWIN drift alerts and a model-age kill switch.
4. Each retrain produces a challenger, which runs in shadow beside the champion. It is promoted only if it wins on purged CV and Deflated Sharpe net of 2× costs.
5. **Modality ablation on every retrain:** train with and without each channel and report the incremental lift. A channel with no significant lift is masked off automatically.
6. Curriculum: stage 0 market + forecast, stage 1 adds raw text, stage 2 adds Claude insights once the threshold is met.

**Baselines every version must beat:** volatility-scaled multi-lookback trend, HAR volatility sizing [track 11], and LightGBM on the same inputs (including PCA-reduced text embeddings and insight fields). Track 04 found trees often beat deep nets on medium-sized tabular data, and it gathered no controlled evidence that text embeddings add alpha beyond price features. If the fusion network doesn't beat LightGBM-with-embeddings, keep LightGBM behind the same pipeline; the architecture does not change.

**Leakage controls**
- Insights use only data with `ingested_at` ≤ the decision time; prompts exclude prices and outcomes after it.
- No pre-June-2026 history for the Claude channel.
- **Forecasting-model contamination:** Chronos-2 and TimesFM were pretrained on large corpora that may include your test periods. I haven't checked their training windows, so also evaluate the forecast channel on periods after their release dates.
- Purge and embargo by label horizon; MLflow logs every experiment so the trial count for Deflated Sharpe is honest.

**Compute on M4 16 GB.** Measured on 2026-11-14 (`docs/benchmark-m4.md`): a 39k-parameter GRU trains at about 14k samples/s on PyTorch MPS and a 0.8M-parameter Transformer at about 1.6k to 3.4k samples/s on any backend, with peak memory under 800 MiB. Use PyTorch (MPS for GRU or TCN) as the default; MLX is for inference of ported models. Embeddings run as a nightly batch. Chronos-2, TimesFM 2.5 and TinyTimeMixer all fit [track 10]. Retraining runs overnight, one heavy job at a time.

### 4.4 Risk gate

Separate process, deterministic, no network, limits in a hash-pinned read-only file. It can tighten model/agent input but never loosen it. Starting defaults, to validate in Phase 1:

| Control | Starting value | Status |
|---|---|---|
| Risk per trade | 0.25–0.5% of equity | Starting point |
| Account halt | 15% drawdown | Derived in Phase 1, approved by you 2026-11-14 (minimal profile, `config/limits.toml`) |
| Daily loss halt | 2.5% | Same |
| Exposure cap | 20% of equity in crypto at once | Same. Chosen because a repeat of the worst 24-hour fall (x1.5) still fits inside the 15% halt |
| Net factor caps | Crypto beta, USD/real-rate exposure | Caps because BTC-gold correlation was 0.42 in 2026 vs 0.06–0.14 before [track 11, unverified] |
| Cost gate | Skip trades whose expected edge < k × round-trip cost | Required |
| Min-size rule | Skip if the broker's minimum size overshoots the risk budget | Required; see below |
| Conduct guard | Self-trade prevention, minimum order lifetime, cap on cancel-to-fill ratio | Required by Binance's API terms (no wash trading or spoofing); see `docs/binance-terms-review.md` |
| Kill switch | Flatten + cancel all, one command, works offline | Must be tested in Phase 4 |

**Small-account reality [own calc, assumptions stated].** At $500 with 0.5% risk per trade, the budget is $2.50. Assuming a standard 0.01 lot of XAUUSD is 1 oz (check your broker) and gold is around $3,900–4,000, a $25 stop costs $25, or 5% of the account. So the min-size rule will skip most gold trades unless the broker offers cent or micro contracts. EURUSD at 0.01 lot is about $0.10 per pip, so a 20-pip stop is about $2, which fits. Crypto spot at this size is fine as long as the exchange minimum notional is small [verify]. Round-trip fees on Binance spot are 0.2% before any discount [verify]; a daily strategy can absorb that, an hourly one cannot.

### 4.5 Execution

- **Broker interface:** `submit`, `cancel`, `positions`, `balances`, `stream`. Implementations: `SimBroker` (backtest and paper), `BinanceBroker`, `CTraderBroker`, `Mt5Broker`.
- **Binance:** build on Spot first (OCO available). USDⓈ-M futures conditional orders moved to `/fapi/v1/algoOrder` on 2025-12-09 and broke several libraries; futures has no native OCO, so orphaned stops are a bug class. Futures eligibility for you is unconfirmed [track 08]. Use the Spot Testnet for development; assume testnets don't model funding or slippage.
- **cTrader first for FX/gold:** Open API runs natively on macOS (52 brokers listed for Sri Lanka [track 08]). The official Python client (`ctrader-open-api` 0.9.2, MIT) was last pushed 2024-08-07, so test on a demo account first and be ready to write a thin client over the protobuf protocol.
- **MT5 second:** the official `MetaTrader5` package ships only `win_amd64` wheels (verified), so it needs Windows. Run a tiny gateway on a small Windows VPS over Tailscale, with server-side SL/TP on every order. Wine on the Mac is not recommended (a macOS 26.5 crash was reported, your version [track 09]). Write your own gateway; MetaQuotes took down bridge repos in 2023.
- **Framework decision:** thin custom event-driven engine (track 09). NautilusTrader is Plan B: it has no MT5 adapter, is mid v1→v2, and an open Binance bug (#5664, filed 2026-11-13) affects it. vectorbt for research only.
- **Approval flow:** each proposed order prints in the terminal with its risk-gate verdict; you approve or reject. No auto-submit in v1.

### 4.6 Operations on the Mac mini

The agent reported this Mac is set to `sleep 1`, `autorestart 0` and auto-installs macOS updates [track 09]. Before any live trading:
- disable sleep (`pmset`), enable auto-restart after power loss, disable automatic macOS restarts for updates;
- run every process under `launchd` with restart-on-crash;
- external heartbeat: a ping every minute to a free dead-man's-switch service, so silence alerts you. **Recommendation:** add outbound-only Telegram alerts before live, even though you chose terminal-only; a stopped process while you are away is otherwise invisible;
- secrets in macOS Keychain; keys never in env files or the repo;
- weekly snapshot of the ledger and state to an external drive.

**Memory schedule (one heavy job at a time):**

| Time | Job |
|---|---|
| Continuous, light | Collectors, risk gate, execution (about 1–2 GB) |
| Hourly | Pre-filter (dedupe, embeddings, FinBERT), then a Haiku batch for the surviving items |
| Daily, once | Claude briefing (API) and ledger scoring |
| Nightly | Retraining, backtests, MLflow (CPU/MPS, no LLM loaded) |

---

### 4.7 Observability

Everything above is only useful if you can see what it did and why. This section is a design proposal; I did not research tools for it, so tool names are suggestions to verify.

**Principles**
1. **One thread through everything.** Each decision gets a `decision_id`, and every event it touches carries it, plus the `item_id`s of the news that fed it. Any trade can be replayed from headline to outcome.
2. **The event log is the source of truth.** Append-only structured events (JSON lines) are loaded into an `events` table in DuckDB. Dashboards, alerts and the status screen are all derived from it.
3. **Observe from outside the trading path.** The watchdog is a separate process. A dead trading process must not be able to silence its own alarm, so an external heartbeat service (outside the Mac) alerts when pings stop.
4. **Local and light.** Terminal first, as you chose: a `getrich status` screen. Optional later: a local Grafana over DuckDB. No SaaS log storage.
5. **Every alert says what to do.** An alert without an action is noise.
6. **Label rejected trades too.** A decision the risk gate rejects still gets a counterfactual outcome label from prices, so the training data isn't limited to trades you happened to take.

**What is observed**

| Area | Signals | Example alert |
|---|---|---|
| Data pipeline | Per-source lag, bar gaps, duplicate bars, row counts, news items per hour, dedupe rate, `ingested_at` vs `published_at` skew | Binance daily bar not updated 2 min after close |
| Agents and Claude | Calls, tokens, cost per call and per day, spend vs monthly cap, schema-validation failures, prompt-injection flags, insights written | Month-to-date spend above 80% of cap |
| Models | Feature drift (PSI/KS), calibration curve, live vs backtest drift, per-channel lift from the ablation, champion/challenger scores, model age | Calibration error above threshold on the last 100 resolved rows |
| Risk and execution | Every risk verdict with reason codes, approvals and approval latency, order lifecycle, slippage vs the cost model, position reconciliation, exposure vs caps, drawdown vs halt, kill-switch state | Reconciliation mismatch with the exchange |
| P&L | Equity, drawdown, attribution by strategy, model version and channel, cost drag | Daily loss approaching the halt limit |
| System | Process heartbeats, restarts, disk free, memory, sleep events, clock drift (NTP), network and broker connectivity | Disk free below 10 GiB (47 GiB today) |

**Alert tiers (starting points to tune).** P0, act now: kill switch tripped, position without a server-side stop, reconciliation mismatch, heartbeat lost. P1, within the hour: data stale, drift, spend over 80% of cap, broker quote stale. P2, daily digest: everything else worth reading.

**Storage [own calc, assumes about 50k events/day at about 500 B each].** About 9 GB a year as raw JSON lines, which compresses to roughly 1–2 GB a year as Parquet. Keep 30 days of raw logs, and decisions and ledger rows forever. Given 47 GiB free, the log volume is fine.

**Suggested tools [not researched]:** `structlog` for JSON events, DuckDB for the events table, Rich or Textual for the status screen, MLflow (SQLite) for experiments, an external dead-man's-switch service for the heartbeat, and outbound-only Telegram alerts before any live trading.

---

## 5. Repository layout (proposed)

```
project-get-rich/
  research/            # existing reports
  ARCHITECTURE.md
  src/getrich/
    collectors/        # binance, dukascopy, macro, news
    store/             # duckdb + parquet schemas, bitemporal news
    extract/           # local pre-filter, Claude (Haiku) extraction, ledger
    features/ models/ eval/   # baselines, PI model, CPCV, metrics
    risk/              # separate-process gate, limits.toml (hash-pinned)
    exec/              # Broker interface + sim, binance, ctrader, mt5 client
    ops/               # launchd plists, heartbeat, kill switch
    obs/               # event schema, log writer, status screen, alert rules, watchdog
  gateways/mt5/        # Windows-only MT5 gateway (runs on the VPS)
  tests/               # incl. fault-injection and kill-switch tests
```

Tooling: Python with `uv`, DuckDB, LightGBM, PyTorch MPS or MLX, MLflow (SQLite), Optuna (SQLite), launchd.

---

## 6. Roadmap and gates

Time estimates are my rough guesses at 10+ hours/week; gate thresholds are suggestions to tune, not research findings.

| Phase | About | Work | Gate |
|---|---|---|---|
| **0 Foundations** | 1–2 weeks | Repo, store, collectors, **news/insight recorder running unattended**, **event log with `decision_id`, hash-chained insight ledger, status screen, external heartbeat, `getrich gate` exit checker**, Mac mini hardening, MPS-vs-MLX one-hour test | Recorder runs a week unattended; data reproducible; killing a process raises an alert |
| **1 Evaluation harness** | 2–3 weeks | Cost model, purged CV/CPCV, Deflated Sharpe, trend and HAR baselines on BTC/ETH; derive drawdown and loss limits from backtests and stress scenarios | Harness rejects shuffled labels; you approve the drawdown limits **Status 2026-11-14: built and validated; limits approved, minimal profile (docs/phase1-findings.md).** |
| **2 PI-Net v1: market + forecast** | 3–4 weeks | Triple-barrier labels, outcome labeler, LightGBM baseline, then small fusion net with market and forecast channels, dense auxiliary targets, permutation test | Beats baselines net of 2× costs under CPCV; DSR positive |
| **2b Raw-text channel** | 2–3 weeks | Backfill GDELT/RSS history, frozen embeddings, attention pooling, modality ablation | Text channel shows incremental CPCV lift over 2, or it stays masked |
| **3 Agents in shadow, then Claude channel** | Ongoing, starts in Phase 0 | Briefings and flags, then journal, then shadow signals, all scored in the ledger. Switch on the Claude-insight channel once the resolved-event threshold is met | Insight channel adds out-of-sample lift on forward data (needs months of recording) |
| **4 Risk gate + Binance testnet** | 3 weeks | Risk gate process, broker interface, `SimBroker` and `BinanceBroker`, CLI approvals, kill switch, fault injection, **alert rules and reconciliation checks** | No unintended orders under faults; reconciliation matches the exchange; every injected fault shows up in the event log and raises the right alert |
| **5 cTrader demo (+ MT5 gateway spike)** | 3–4 weeks | `CTraderBroker` on a demo account; MT5 gateway only if cTrader proves unsuitable | Demo fills reconcile; spread and swap costs measured |
| **6 Micro-live: crypto** | Several weeks | Smallest sizes, every order approved by you, real costs logged | Live within tolerance of paper after real costs; limits respected |
| **7 Micro-live: gold/FX** | After Phase 6 | Same, under your legal decision and the min-size rule | Same as Phase 6 |

---

## 7. Open risks and unknowns

1. **Legal/funding (Sri Lanka).** CBSL's 2019 notice says residents are "not permitted" to trade forex or remit funds abroad for it; crypto is grey, with a VASP regime approved by Cabinet but not yet law; a PFCA remittance cap expires about 20 Dec 2026 [track 08, extracted from CBSL and gazette text by the agent, not re-read by me]. You have chosen to handle this; confirm it with a lawyer and an accountant before real money moves.
2. **Binance:** futures eligibility and production API availability for Sri Lankan accounts are unconfirmed [track 08]. The API terms were read on 2026-11-14 (`docs/binance-terms-review.md`): automated trading with keys is allowed, with conduct rules and key-handling duties. Whether storing public market data is covered is not addressed.
3. **cTrader:** which broker, whether it enables the Open API for you, and real XAUUSD/EURUSD spreads and Sri Lanka funding routes are unverified for every broker [track 08]; the official Python client is stale.
4. **Data licences:** Binance Vision (see 4.1); Dukascopy and news-feed terms unread.
5. **Crypto structure risk:** the 10 Oct 2025 crash liquidated over $19B and some collateral tokens depegged on Binance only [track 11, causation disputed]. Plan for exchange-specific tail risk and stablecoin risk.
6. **Gold regime:** 2026 gold facts are blog-grade [track 11]; do not hard-code gold as a hedge.
7. **Disk:** 47 GiB free on a 228 GiB SSD [track 10].
8. **Evidence gap:** no confirmation post-2022 for most crypto papers cited in track 11; Reddit, X and Instagram were unreachable throughout.
