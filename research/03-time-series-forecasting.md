# 03 - Time-Series Forecasting for Stocks, FX and Metals

Researcher track 3 of 7. Date of research: 2026-11-14.
Constraint applied (from coordinator): LOCAL-FIRST. Only Anthropic Claude may be a cloud LLM; every forecasting model must run locally. Hardware assumed: Apple Silicon Mac (this is an assumption, not verified against the user's machine).

Evidence conventions: "Seen" means I read it on the page/abstract during this session. "Unverified" means from a secondary source or my own background knowledge. GitHub star counts were read from repo front pages on 2026-11-14. I could NOT obtain last-commit dates (GitHub pages fetched did not show them; GitHub API was rate-limited), so those are marked "n/a". Where I use version/news dates they come from the READMEs.

---

## 1. TL;DR

1. Forecasting raw price/returns directionally is, on the best current evidence, a near-zero-edge problem for zero-shot foundation models (TSFMs). Five independent 2025-2026 studies and several practitioner repos find the models at or below a random walk / no-change forecast on stocks and index futures. See section 4.
2. What does carry signal: volatility (GARCH/HAR family are hard to beat; TSFMs mostly do not beat Log-HAR), cross-sectional ranking (Gu-Kelly-Xiu style, small but real), time-series momentum/trend and carry (documented risk premia, not point forecasts), and seasonality in non-price series. FX and gold: random walk remains the toughest benchmark.
3. So the forecasting layer should NOT be sold as "price predictor". It should be a feature/uncertainty provider: calibrated volatility + quantile forecasts + a few cheap momentum/carry/seasonality features, feeding the user's profitability-index classifier and the risk layer. TSFM outputs are optional features to be tested, not assumed.
4. Evaluation matters more than model choice. Use purged/embargoed walk-forward and CPCV, report Deflated Sharpe and PBO, compare against no-change, historical-mean and Log-HAR baselines, and include costs. Every positive result should be treated as a false discovery until it survives that.
5. Local-first picks (Apple Silicon): Chronos-2 (120M, Apache-2.0, MLX port exists) and Chronos-Bolt for general quantile forecasts; TimesFM 2.5 (Apache-2.0) over TimesFM 3.0 (non-commercial weights); TTM (tiny, Apache-2.0, CPU) especially for volatility; Toto 2.0 small sizes and TiRex-2 as optional extras; Kronos as a candlestick-native research candidate (MIT, MLX port) with weak independent evidence. TimeGPT is cloud-only: out of scope.
6. Classical stack still earns its place: `arch` (GARCH family, HAR), StatsForecast (fast baselines), LightGBM/MLForecast, and skfolio for CPCV.

---

## 2. Time-series foundation models (TSFMs)

Stars/forks from GitHub front pages on 2026-11-14. License = the license I saw for code; weights license noted separately when different.

| Model | Repo / URL | Stars | License (code / weights) | Params | Context | Probabilistic? | Fine-tune | Finance-specific evidence |
|---|---|---|---|---|---|---|---|---|
| TimesFM 1.0 / 2.0 / 2.5 / 3.0 (Google) | https://github.com/google-research/timesfm | 35.5k | Code Apache-2.0. Weights Apache-2.0 up to 2.5; **3.0 weights non-commercial, non-production** (README) | 2.0: 500M; 2.5: 200M; 3.0: 330M (README) | 2.0: 2,048; 2.5: up to 16k; 3.0: 15,360 | 2.5: optional 30M quantile head; 3.0: point + 9 quantiles | LoRA example (HF PEFT) added Apr 9, 2026 | None from Google. Third-party: sec. 4 (coin-flip on direction) |
| Chronos (T5), Chronos-Bolt, Chronos-2 (Amazon) | https://github.com/amazon-science/chronos-forecasting | 6.3k | Apache-2.0 (README text; a badge says MIT, conflict noted). Chronos-2 card: Apache-2.0 | Chronos-2 120M, Chronos-2-small 28M, Bolt 9M/21M/48M/205M, T5 8M-710M | Chronos-2: 8,192 in / 1,024 out (model card) | Yes: quantiles (Bolt, Chronos-2); sampling (T5) | AutoGluon / not in the README I read | Third-party only (Rahimikia et al.: weak zero-shot) |
| Moirai 1.0/1.1, Moirai-MoE, Moirai 2.0 (Salesforce) | https://github.com/SalesforceAIResearch/uni2ts | 1.6k | Code Apache-2.0. Moirai 2.0 weights reported CC BY-NC 4.0 (secondary source, unverified) | Moirai 2.0 small ~11M (secondary, unverified); others not stated on README | n/a | Yes (samples) | Yes via `cli.train` | Noguer i Alonso & Franklin 2026: Moirai-2.0 among best average ranks on 5 US equities but gains vs random walk small/sparse |
| Lag-Llama | https://github.com/time-series-foundation-models/lag-llama | 1.6k | Apache-2.0 | n/a | 32 train; up to 1024 suggested | Yes | Yes | None seen. Last dated update on README June 2024 - effectively stale |
| TinyTimeMixer / Granite TS (IBM) | https://github.com/ibm-granite/granite-tsfm ; HF `ibm-granite/granite-timeseries-ttm-r2` | 919 | Apache-2.0 | ~1M-scale (model card says "from 1M"; metadata ~805k) | 512 / 1024 / 1536 | Not stated (point forecasts) | Yes (few-shot ~5% data) | Brini 2026 (RV): TTM was the only TSFM to beat Log-HAR at every horizon, narrowly. README: IBM says repo will not be maintained going forward |
| Toto 1.0 / 2.0 (Datadog) | https://github.com/DataDog/toto | 572 | Apache-2.0 (code and the 313m card) | 2.0: 4M, 22M, 313M, 1B, 2.5B; 1.0: 151M | quick-start 512 | 1.0: Student-T mixture; 2.0: 9 quantiles | 1.0 yes; **2.0 not yet** | Tested zero-shot in moneyheap repo: coin-flip direction |
| TiRex (NX-AI) | https://github.com/NX-AI/tirex | 308 | "NXAI community license" (terms not stated on page; unverified) | 35M (xLSTM) | n/a | Yes (quantiles + mean) | Not public | Used in index-futures study: did not beat no-change |
| TiRex-2 (NX-AI) | https://github.com/NX-AI/tirex-2 | 164 | Apache-2.0 | 38.4M active univariate, +44.1M for multivariate | n/a | n/a on page | n/a | Claims NeurIPS 2026 oral; no finance numbers |
| Kronos (Tsinghua; AAAI 2026) | https://github.com/shiyu-coder/Kronos ; arXiv 2508.02739 | 47.8k | MIT | mini 4.1M, small 24.7M, base 102.3M (open); large 499.2M NOT open | mini 2048, small/base 512 | Sampling (T, top_p, sample_count) | Yes (Qlib-based scripts, A-shares daily example) | Paper: RankIC +93% vs best TSFM, vol MAE -9% (abstract). Independent tests are negative/inconclusive (sec. 4.5) |
| Time-MoE | https://github.com/Time-MoE/Time-MoE | ~1.0k | Apache-2.0 | 50M, 200M checkpoints (2.4B announced, not linked) | 4,096 | No (point) | Yes | None. Pins `transformers==4.40.1` (dated) |
| Sundial (Tsinghua; ICML 2025 oral) | https://github.com/thuml/Sundial | 235 | Apache-2.0 | ~128M ("sundial-base-128m") | 2,880 used in examples | Yes (generative flow-matching samples) | Not yet released | None seen |
| TimeGPT / TimeGPT-2 (Nixtla) | https://www.nixtla.io/blog/timegpt-2-announcement | n/a | Proprietary API | n/a | n/a | n/a | n/a | Evaluated in Noguer i Alonso & Franklin 2026. **CLOUD-ONLY: out of scope** |

Notes on newer 2026 releases (seen):
- TimesFM 3.0 (Aug 2026): 330M, native multivariate and covariates, #1 on fev-bench / TIME / GIFT-Eval per Google's README. Weights are non-commercial, non-production. Commercial use routed via BigQuery ML (README). Secondary reports date weights availability to Aug 31, 2026.
- Toto 2.0 (Apr 2026): arXiv 2605.20119; paper claims SOTA on GIFT-Eval, BOOM, TIME (fine-tuned/ensemble variants top overall). Leaderboards are time-dependent (a Sept 2026 paper snapshot, arXiv 2609.28506, notes continuous updates).
- Chronos-2 (Oct 20, 2025): zero-shot univariate, multivariate, covariate-informed.
- TiRex-2 (arXiv 2607.01204; Sep 2026 news on README).
- Moirai 2.0 (Aug 2025 release; arXiv 2511.11698).
- Nixtla raised $16M Series A on Feb 5, 2026; TimeGPT-2 Mini/2/Pro in private preview (pilot programs, waitlist). Cloud-only.
- Darts now lists Chronos2Model, TimesFM2p5Model, TimesFM3Model, TiRexModel, TiRex2Model, PatchTSTFMModel, T0Model wrappers (README), which is a convenient unified local interface.

Benchmark caveat: GIFT-Eval / fev-bench ranks are general (energy, sales, web traffic...). FinVerse (arXiv 2608.03259, 43 TSFMs, 116,897 financial series) found rank agreement with GIFT-Eval of only r = 0.43. Do not pick a model for finance by GIFT-Eval rank.

Finance-domain pretraining option: FinText (Rahimikia et al.) publishes Chronos-architecture models pretrained on US financial series with a year cutoff in the name (for example `FinText/Chronos_Small_2018_US`, trained on US data 1990-2018, Apache-2.0). URLs: https://huggingface.co/FinText/Chronos_Small_2018_US . This addresses the lookahead issue by providing vintage models. I saw no performance claims on the card; the supporting paper (arXiv 2511.18578) says models pre-trained from scratch on financial data improved substantially over off-the-shelf TSFMs.

---

## 3. Libraries (classical + deep)

Stars from GitHub front pages 2026-11-14. Last commit n/a (not shown).

| Library | URL | Stars | License | Notes / sensible? |
|---|---|---|---|---|
| Darts (Unit8) | https://github.com/unit8co/darts | 9.6k | Apache-2.0 | Unified API for classical, deep and the TSFMs above (Chronos-2, TimesFM 2.5/3, TiRex/TiRex-2). Best single wrapper for experimentation. |
| sktime | https://github.com/sktime/sktime | 10.1k | BSD-3-Clause | v1.3.0 banner. Good sklearn-style API, forecasting pipelines, evaluation. No TSFM integration seen on page. |
| StatsForecast (Nixtla) | https://github.com/Nixtla/statsforecast | ~5.0k | Apache-2.0 | Fast AutoARIMA/ETS/Theta; also GARCH/ARCH. Good baseline factory (CPU). |
| NeuralForecast (Nixtla) | https://github.com/Nixtla/neuralforecast | 4.3k | Apache-2.0 | NHITS, NBEATS, PatchTST, TFT, iTransformer, TiDE, DeepAR, etc. Local; use as trained-from-scratch baselines. |
| MLForecast (Nixtla) | https://github.com/Nixtla/mlforecast | 1.3k | Apache-2.0 | LightGBM/XGBoost with lag features; the usual strong tabular baseline. |
| GluonTS (AWS) | https://github.com/awslabs/gluonts | 5.3k | Apache-2.0 | Probabilistic framework (DeepAR etc.); Python 3.10-3.14 supported; large open-issue count. Useful for CRPS/metrics, otherwise lower priority. |
| PyTorch Forecasting | https://github.com/sktime/pytorch-forecasting | 5.0k | MIT | TFT, N-HiTS, DeepAR, PatchTST. 636 open issues; works but heavy for the small-signal finance problem. |
| Prophet | https://github.com/facebook/prophet | 20.5k | MIT | README: "maintenance mode as of v1.4.0"; v1.5.0 dated 2026.10.05 in changelog. Wrong tool for markets (designed for business seasonality). Skip. |
| arch (Kevin Sheppard) | https://github.com/bashtage/arch | 1.7k | license not named on page (verify; historically NCSA) | GARCH, EGARCH, TARCH, APARCH, FIGARCH, HAR mean models, EWMA, bootstraps. Core for volatility. |
| HAR-RV | Corsi (2009), https://papers.ssrn.com/abstract=1365738 | - | - | Implement as OLS on daily/weekly/monthly realized-vol averages (or use `arch` HAR). Needs intraday data for realized variance; can use range-based estimators from daily OHLC if intraday is unavailable. |
| PatchTST, N-HiTS, TFT | via NeuralForecast / PyTorch Forecasting / granite-tsfm | - | - | Papers are fine; architectures are available in the libraries above. No evidence these beat simple baselines on returns (see Andreoletti 2026). |
| skfolio | https://github.com/skfolio/skfolio | 2.6k | BSD-3-Clause | Portfolio optimization with `WalkForward`, `CombinatorialPurgedCV`, `MultipleRandomizedCV`. Page does not mention Deflated Sharpe. |

Repos that bundle forecasting + trading (brief):
- Qlib (Microsoft): https://github.com/microsoft/qlib - 50.3k stars, MIT, "active and continuing development"; models include LightGBM/XGBoost/CatBoost, LSTM/GRU, TFT, Transformer, TCN etc.; RD-Agent for automated factor/model R&D; official dataset temporarily disabled; recent breaking change requires `trusted=True` for artifact loading (migration guide on README). Kronos fine-tuning pipeline uses Qlib data.
- FinRL: https://github.com/AI4Finance-Foundation/FinRL - 17.1k stars, MIT (trademark restricted); README directs production users to FinRL-X; last release listed 0.3.5 (2022); educational/research. Data sources include Alpaca, Yahoo, Binance, FXMacroData.

---

## 4. The hard truth: what is and is not predictable

### 4.1 TSFMs on returns: zero-shot is about a random walk

Primary, rigorous sources (all seen via arXiv abstract pages, 2026-11-14):

- Upadhyay, "Do Time-Series Foundation Models Forecast Index-Futures Returns? A Preregistered Evaluation..." arXiv 2611.12141 (9 Nov 2026), https://arxiv.org/abs/2611.12141 . Chronos-Bolt, Chronos-2, TimesFM 2.5, Moirai 2.0, TiRex vs no-change on E-mini NQ/ES, 5-120 min. **0 of 160 model/representation/horizon/market cells beat no-change** on the blind test; Hansen SPA p = 1.000; 0 of 120 on a later hold-out. Price-level correlation above 0.9996 and RankIC +0.35 at 30 min are artifacts (a sign-randomised null reproduces ~95% of the RankIC). A ridge regression did about as well as TSFMs. One model beat HAR on 5-minute volatility but not the EWMA already in its input.
- Rahimikia, Ni, Wang, "Re(Visiting) Time Series Foundation Models in Finance," arXiv 2511.18578 (Nov 2025), https://arxiv.org/abs/2511.18578 . Daily global excess returns. Off-the-shelf pre-trained TSFMs "perform poorly in zero-shot and fine-tuning settings"; models pre-trained from scratch on financial data give substantial improvements. Numbers I saw only via a secondary search snippet of the conference version (https://wp.lancs.ac.uk/fofi2026/files/2026/03/FoFI-2026-020-Eghbal-Rahimikia.pdf): out-of-sample R^2 about -1.37% (large Chronos) and -2.80% (TimesFM 500M), directional accuracy about 51% - marked unverified.
- Noguer i Alonso & Franklin, "Pretrained TSFMs for Financial Return Forecasting," arXiv 2606.27100 (Jun 2026), https://arxiv.org/abs/2606.27100 . Five US equities. Pretrained models won 8 of 10 task comparisons vs from-scratch nets (Moirai-2.0 and TimesFM-2.5 best average ranks), but **gains over random walk were small and sparse**; a one-sided Diebold-Mariano test rejected only for Chronos on AMZN and Moirai-2.0 on GOOG. Authors: not "universal engines for statistically reliable alpha generation."
- Brini, "Forecasting Realized Volatility with TSFMs," arXiv 2607.05291 (Jul 2026), https://arxiv.org/abs/2607.05291 . 9 TSFMs vs 8 econometric specs, 50 assets (equities, FX, futures). Only Tiny Time Mixers beat Log-HAR at every horizon, and narrowly; short-horizon advantages largely from better scaling; a 50/50 TTM + Log-HAR blend entered the Model Confidence Set for 98-100% of assets.
- Andreoletti, "Forecast collapse of transformer-based models under squared loss in financial time series," arXiv 2604.00064, https://arxiv.org/abs/2604.00064 . When the conditional mean is near degenerate, expressive models add variance; high-frequency EUR/USD transformers lost to a simple linear benchmark on most windows.
- FinVerse, arXiv 2608.03259, https://arxiv.org/abs/2608.03259 : 43 TSFMs; ranking agreement with GIFT-Eval r = 0.43; argues for direction, cross-sectional ranking and portfolio metrics.
- Zhu & Cai, "Artificial Intelligence in Equity and Crypto Markets," arXiv 2609.04917 (Sep 2026), https://arxiv.org/abs/2609.04917 : critical review; progress mostly upstream (prediction, text); durable net performance evidence is thin; "no general AI architecture in the examined public evidence shows persistent, cross-regime, capacity-aware net alpha."

### 4.2 Practitioner-grade replications (lower rigor, still informative)

- moneyheap/tsfm-stocks (MIT, 4 stars): TimesFM 3.0, Chronos-2, Toto 2.0 313m zero-shot on 24 US tickers, 504 days from 1 Nov 2024. Next-day direction 49.9-51.1% vs always-up 52.2%; error slightly larger than no-change at 1/5/20 days; forecast-vs-actual correlation -0.02 to -0.01; simulated random walks scored the same; 10-90% bands covered 72-80% vs 79-82% for a simple 60-day-vol range; hourly and 5-minute coin-flip. Caveat: one mostly-rising period, possible pretraining overlap. https://github.com/moneyheap/tsfm-stocks
- What Works in Trading Substack (2026-05-05): TimesFM 1.0 200M on top-50 US large caps, purged walk-forward (21-day purge, 5-day embargo), ~12 bps round trip. Standalone Sharpe 0.958 vs SPY 0.458 with drawdowns above 45%; as a filter on a 12-month momentum strategy Sharpe rose from 0.327 to 0.597 (and 0.711 with Kelly sizing). PSR/DSR figures were in images I could not read. Author calls it "a useful second opinion", expects 0.5-0.7 Sharpe realistically. This is a single-author blog; treat as hypothesis, not evidence. https://whatworksintrading.substack.com/p/does-this-large-language-model-made

### 4.3 Classical evidence: what is and is not predictable

- Equity premium/market timing: Welch & Goyal (RFS 2008) found none of the predictors examined beat the running historical mean out-of-sample, most did worse (https://www.nber.org/papers/w10483). Goyal-Welch-Zafirov update (RFS 2024) finds a mixed picture: over a third of new variables lose in-sample significance, half of the rest have poor out-of-sample performance, a few remain useful (https://www.sfi.ch/en/publications/a-comprehensive-2022-look-at-the-empirical-performance-of-equity-premium-prediction).
- Cross-sectional ML: Gu, Kelly, Xiu, "Empirical Asset Pricing via Machine Learning," RFS 33(5), 2020, https://www.nber.org/papers/w25398 . Trees and nets best, from nonlinear interactions; dominant signals are momentum, liquidity, volatility. A neural-net-timed S&P strategy Sharpe 0.77 vs 0.51 buy-and-hold, and an NN long-short decile Sharpe 1.35 in a working-paper version (both from a search snippet of AQR-hosted copies; unverified). I could not extract Table 1 out-of-sample R^2 values from the PDFs in this session; I recall monthly R^2 in the fractions-of-a-percent range, but treat that as unverified. Key lesson: the edge is in cross-sectional ranks of thousands of stocks with many characteristics, not in single-asset price forecasting, and it is concentrated in small/illiquid names where costs bite.
- Time-series momentum: Moskowitz, Ooi, Pedersen, JFE 104(2), 2012: 58 liquid futures/forwards (equity indices, currencies, commodities, bonds); past 12-month excess return positively predicts the next period; persists about a year then partially reverses (https://papers.ssrn.com/abstract=2089463). This is a risk-premium/trend feature, not a TSFM output, and it is the most credible "directional" signal for FX and metals futures.
- FX carry: Lustig, Roussanov, Verdelhan, RFS 24(11), 2011: carry (high minus low interest-rate currencies) is a priced risk factor; annualized Sharpe about 0.6 in one abstract (https://www.nber.org/papers/w14082.pdf). Carry is a known, crash-prone premium, not a forecast.
- FX point forecasts: Rossi (2013, JEL 51(4)) survey: the Meese-Rogoff result stands as the standard reference; the driftless random walk is the toughest benchmark; predictability "depends" on predictor, horizon, sample, model; clearest with Taylor-rule or net-foreign-asset predictors in small linear models (https://econ-papers.upf.edu/papers/1369.pdf).
- Gold: Hassani, Silva, Gupta, Segnon found no technique beating the random walk at 1- and 9-step horizons for returns; other studies (e.g. Aye et al. 2015 with dynamic model averaging over 28 predictors) report gains, often vs historical mean and sensitive to sample. Net: weak and inconsistent (https://www.up.ac.za/media/shared/Legacy/sitefiles/file/40/677/wp_2014_15.pdf , https://repository.up.ac.za/handle/2263/45456).
- Volatility: Hansen & Lunde, "Does anything beat a GARCH(1,1)?" J. Applied Econometrics 20(7), 2005: 330 ARCH-type models; on exchange-rate data nothing beat GARCH(1,1); on IBM stock, GARCH(1,1) was inferior to leverage-capable models (https://econpapers.repec.org/RePEc:jae:japmet:v:20:y:2005:i:7:p:873-889). Corsi (2009) HAR-RV is the standard realized-vol benchmark (https://papers.ssrn.com/abstract=1365738). Brini 2026 (above) shows TSFMs rarely beat Log-HAR.

### 4.4 Summary table

| Target | Evidence | Verdict |
|---|---|---|
| Next-bar/next-day price or return level, single asset | Sections 4.1-4.2, Welch-Goyal, Rossi | Not reliably predictable; no-change/historical-mean is the benchmark to beat |
| Direction (sign) | 49.9-51.1% in moneyheap; ~51% in Rahimikia (unverified) | ~Coin-flip; always-up beats models in a bull sample |
| Realized volatility / variance | Hansen-Lunde, Corsi, Brini | Predictable; use GARCH/HAR; TSFMs add little (TTM + HAR blend is the best-evidenced hybrid) |
| Cross-sectional rank (equities) | Gu-Kelly-Xiu | Small but real; needs wide universe, costs matter |
| Trend/time-series momentum in futures/FX/metals | Moskowitz-Ooi-Pedersen | Documented premium; modest, regime-dependent |
| FX carry | Lustig et al. | Premium with crash risk |
| Regimes (vol/correlation states) | Vol clustering literature (above) | Plausibly predictable, evidence in this track is indirect |
| Calibrated forecast distributions | moneyheap: coverage 72-80% vs 79-82% simple vol range; kronos-market-eval: p10-p90 coverage 21-43% | TSFM intervals can be badly miscalibrated; must be recalibrated (conformal) |

### 4.5 Kronos specifically

Kronos (https://github.com/shiyu-coder/Kronos; arXiv 2508.02739; AAAI 2026) is a decoder-only model for OHLCV candles: a tokenizer quantizes K-line data into discrete tokens, then an autoregressive transformer is pretrained (paper abstract: over 12B K-line records, 45 exchanges). README calls it "the first open-source foundation model for financial candlesticks" and says the fine-tuning example is "not a production-ready quantitative trading system"; the demo strategy ignores costs/slippage/impact; the largest model is not open.
Paper claims (abstract): RankIC +93% vs leading TSFM, +87% vs best non-pretrained baseline; volatility MAE -9%; synthetic K-line fidelity +22%.
Independent checks (all informal, not peer reviewed):
- sumit-ai-ml/kronos-market-eval (6 stars, MIT, run 2026-08-04): Kronos-base vs random walk. BTC 24h: skill -118%, direction 50/100, p10-p90 coverage 21%. SPY 1 session: skill -42.5%, direction 28/60, coverage 43%. Fine-tuning lowered held-out token loss but made forecasts worse (21 held-out SPY sessions: pretrained +5.6%, ft_2mo -2.8%, ft_3yr -18.6%). https://github.com/sumit-ai-ml/kronos-market-eval
- Substack (2026-07-30) reports: Kronos-small on 13 US stocks, 390 forecasts, 30-min horizon: direction 54.6% vs always-up 54.4% (p~0.92); a volatility study on ~5,000 A-shares had Kronos ranking last, errors 2.4-2.6x HAR-RV (the post's secondary account). https://aidriventrading.substack.com/p/kronos-ai-and-the-real-test-promise
- Upadhyay (arXiv 2611.12141) also tested Kronos in separate experiments; headline conclusion was no incremental skill.
- Leakage concern raised by TSFM.ai (pretraining on many exchanges likely overlaps historical test windows): https://tsfm.ai/blog/kronos-financial-foundation-model (secondary).
Verdict: promising as a research artifact and a candle-native encoder, not as evidence of a tradable edge. Keep as an optional feature generator behind strict tests. Also note Kronos tokenizer-based sampling can give wrong-scale uncertainty (see coverage numbers).

---

## 5. Proper evaluation protocol (recommended)

Sources: Bailey & López de Prado, "The Deflated Sharpe Ratio" (JPM 40(5), 2014; https://papers.ssrn.com/abstract=2460551); Bailey, Borwein, López de Prado, Zhu, "The Probability of Backtest Overfitting" (J. Computational Finance 20(4), https://papers.ssrn.com/abstract=2326253); Arian, Norouzi Mobarekeh, Seco, "Backtest overfitting in the machine learning era" (Knowledge-Based Systems, 2024, DOI 10.1016/j.knosys.2024.112477; abstract: CPCV shows lower PBO and better DSR test statistic than walk-forward, K-fold and purged K-fold in a synthetic environment; walk-forward was worst on false-discovery prevention - abstract-level, I did not read the full paper). Purged/embargoed CV and triple-barrier come from López de Prado's "Advances in Financial Machine Learning" (2018) - from my background knowledge, not re-verified here.

Protocol:
1. Targets with labels that span time (triple-barrier, multi-day returns): purge training samples whose label windows overlap the test fold; add an embargo after each test fold.
2. Model selection: CPCV (skfolio `CombinatorialPurgedCV(n_folds=10, n_test_folds=2)`) to get a distribution of out-of-sample paths, not a single path. Use `WalkForward` for the final, deployment-faithful rehearsal (expanding or rolling window, retrain schedule identical to production).
3. Multiple-testing accounting: log every model/hyper-parameter/feature variant tried (N trials). Compute Deflated Sharpe Ratio with the trial count and return skew/kurtosis; compute PBO via CSCV over the candidate set. skfolio's README does not mention DSR, so implement DSR yourself (about 30 lines with scipy) or use another library (not verified in this session: mlfinlab is commercial/closed-source to my knowledge; `timeseriescv` is a small purged-CV package; I did not check their maintenance, so treat as options to vet).
4. Always include baselines: no-change (price), historical mean (returns), EWMA and Log-HAR (volatility), buy-and-hold, and a simple trend rule. A model that does not beat these is not a model. Test with Diebold-Mariano or Hansen SPA/Model Confidence Set, not point comparisons.
5. Metrics beyond MAE: out-of-sample R^2 vs the benchmark (Campbell-Thompson style), directional accuracy with a binomial test against the base rate (always-up is often 52-54% in bull samples), RankIC/IC with t-stats and a sign-randomised null (Upadhyay shows RankIC can be an artifact), pinball loss/CRPS, interval coverage and calibration, Mincer-Zarnowitz regressions for vol, and economic value: net Sharpe after costs, turnover, max drawdown, DSR.
6. Leakage controls: point-in-time data, survivorship-bias-free universes, adjusted prices handled consistently, and awareness that TSFM pretraining corpora (Kronos, TimesFM, Chronos) may have seen your test period. Prefer test periods after the model's data cutoff (a Kronos follow-up paper cited a June 2024 pretraining cutoff per a search snippet) or vintage models (FinText).
7. Regime reporting: break results out by volatility regime and by year; require stability across at least two regimes.
8. Paper-trade forward test before any live capital, with pre-registered success criteria (the Upadhyay paper is a good template).

---

## 6. Practical design: what to forecast and how it feeds downstream

### 6.1 What to predict (priority order)

1. Volatility (next-day to next-month realized vol, or range-based estimate): GARCH/EGARCH via `arch`, HAR/Log-HAR, optionally blended 50/50 with TTM (Brini). Primary consumer: risk layer (position sizing, stops, vol targeting) and the barrier widths for labeling.
2. Quantiles / predictive distribution of multi-day returns, recalibrated: take TSFM quantiles (Chronos-2, TimesFM 2.5, Toto 2.0) or GARCH-scaled distributions, then apply conformal/quantile recalibration using a rolling window of past residuals. The moneyheap and kronos-market-eval coverage numbers show raw intervals are not trustworthy.
3. Triple-barrier outcome probabilities (hit upper / hit lower / time-out, with barriers scaled by forecast vol): this is the label shape that matches a "profitability index" classifier. Treat TSFM outputs as features to a classifier rather than the classifier itself.
4. Cross-sectional ranks (for the equities sleeve): expected-return rank within a universe from a LightGBM/linear model over momentum, reversal, liquidity, volatility features (Gu-Kelly-Xiu lineage). Evaluate with RankIC and decile spreads after costs.
5. Trend/carry/seasonality features for FX and metals: 12-month time-series momentum sign/magnitude (Moskowitz et al.), carry/forward-points for FX, session/day-of-week effects as features.
6. Raw price/return point forecasts: lowest priority; include only as one feature among many, and only if it clears section 5.

### 6.2 How forecasts should feed the classifier and risk layer

- To the user's encoder+classifier: provide a compact feature vector per (asset, time): forecast vol (GARCH, HAR), vol-of-vol, TSFM median and quantile spreads (q10, q50, q90) normalized by forecast vol, TSFM-vs-naive disagreement, trend/carry/seasonality features, regime indicator (vol percentile). Train the classifier on triple-barrier labels with meta-labeling (primary rule proposes side; classifier decides size/skip), purged CV only.
- Treat forecast dispersion/uncertainty as first-class: a wide TSFM quantile spread or model disagreement should reduce position size, not change direction.
- To risk layer: forecast vol -> vol targeting and stop distances; recalibrated quantiles -> VaR/CVaR estimates; correlation/regime flags.
- Ensembling: equal-weight average of a small set of diverse, locally-runnable models (e.g. Chronos-2 + TimesFM 2.5 + TTM + HAR/GARCH) is the least-overfit way to ensemble; Brini's TTM + Log-HAR blend is an example where simple averaging gave the most consistent model-confidence-set inclusion. Avoid stacking with many learned weights on short samples.
- Keep a "no forecast" fallback: the system should be profitable (or at least safe) with TSFM features switched off; TSFMs are additive options validated by ablation.

---

## 7. Local-first stack (Apple Silicon assumed)

Assumption flag: all hardware notes assume an Apple Silicon Mac (MPS/MLX/CPU). If the user's Mac is Intel, MLX ports will not work; use CPU/ONNX paths. No Nvidia GPU is assumed, so CUDA-only features (TiRex CUDA kernels, flash-attn, Time-MoE flash-attn, Toto xformers) are optional or unavailable.

Inference speed/memory numbers below are only those I actually saw; most models have no verified Mac benchmark. Plan to benchmark on the target machine.

| Model | Runs locally? | Mac path | Verified memory / speed | Weights openly downloadable? License |
|---|---|---|---|---|
| Chronos-Bolt (9M-205M) | Yes | CPU; model cards show device options incl. "mps" (secondary summary); AutoGluon says Bolt suits CPU | No Mac numbers seen. Vendor claim: up to 250x faster and 20x more memory-efficient than same-size original Chronos | Yes, Hugging Face, Apache-2.0 |
| Chronos-2 (120M) / small (28M) | Yes | CPU supported (model card). **MLX port**: `mlx-chronos2` 0.0.1 (May 28, 2026, single maintainer, Apache-2.0 code), https://pypi.org/project/mlx-chronos2/ | MLX memory for 120M: fp32 ~480 MB, bf16 ~240 MB (<0.3% rel. error), int8 ~120 MB (<0.5%), int4 ~60 MB (~6-7% error); bf16 ~1.5x faster than fp32; no absolute latency. Vendor GPU figure: 300+ series/s on one A10G | Yes, Apache-2.0 (model card) |
| TimesFM 2.5 (200M) | Yes | PyTorch CPU; README documents an MLX backend (`pip install timesfm[mlx]`) | README MLX benchmark is for the 330M 3.0 model on M4 Max: ctx 512, horizon 64: batch 1 11.1 ms p50 (90 series/s); batch 32 48.1 ms p50 (666 series/s) | 2.5: Apache-2.0 |
| TimesFM 3.0 (330M) | Yes | MLX backend as above | As above (M4 Max) | **Non-commercial, non-production license**: fine for personal research; legally unclear for a live money-trading system, so prefer 2.5 for anything that trades real money (not legal advice) |
| TTM r2/r2.1 (~1M-scale) | Yes | CPU; model card says laptop/CPU-only machines work | Tiny; no timing seen | Yes, Apache-2.0 (card). IBM says repo no longer maintained |
| Toto 2.0 (4M-2.5B) | Yes | Card: CUDA if available else CPU; MPS not mentioned. Toto 2.0 needs Python 3.12+ | 313M weights ~1.2 GB (F32). 15.4 ms latency is on A100, not Mac. 4M is the edge/CPU tier, 22M the efficient default | Yes, Apache-2.0 |
| TiRex (35M) / TiRex-2 | Yes | README: tested on Linux and macOS; CUDA kernels optional; **ONNX export** for CPU (numpy + onnxruntime); Docker CPU image (TiRex-2) | No numbers | TiRex: NXAI community license (terms unverified, read before commercial use). TiRex-2: Apache-2.0 |
| Moirai 2.0 | Yes | CPU unverified | n/a | CC BY-NC 4.0 reported (secondary): research only |
| Kronos mini/small/base | Yes | PyTorch (README mentions cuda:0 only); community **MLX port** `gxcsoccer/kronos-mlx-base` (MIT; 8-bit quant cuts 390 MB to ~115 MB; no speed figures); .NET TorchSharp port with MPS (NuGet `Kronos.Forecasting`) | Weights sizes only | Mini/small/base: MIT, open. Large: NOT released |
| Sundial (~128M) | Yes | CPU | Reported on Apple M1 Pro 16 GB (README): 249 ms (672-pt lookback, 16-pt forecast) to 949 ms (2880 lookback, 720 forecast, 20 samples) | Yes, Apache-2.0 |
| Time-MoE (50M/200M) | Yes | CPU/GPU; pins transformers 4.40.1 | n/a | Yes, Apache-2.0 |
| Lag-Llama | Yes | CPU | n/a | Yes, Apache-2.0; stale |
| FinText Chronos (finance-pretrained, vintage cutoffs) | Yes | HF Transformers (`AutoModelForSeq2SeqLM`) | n/a | Yes, Apache-2.0 |
| **TimeGPT / TimeGPT-2 (Nixtla)** | **No: cloud API only** | n/a | n/a | **OUT OF SCOPE.** Local alternatives: Chronos-2, TimesFM 2.5, TiRex-2, Toto 2.0 |
| Classical: arch, StatsForecast, MLForecast (LightGBM), NeuralForecast, skfolio | Yes | Pure CPU (NeuralForecast can use MPS via PyTorch; unverified) | Cheap | Open source (licenses in sec. 3) |

Recommended minimal local stack:
- Volatility: `arch` (GARCH/EGARCH) + HAR on daily or intraday-realized variance; TTM blend as optional.
- Quantile forecaster: Chronos-2 (MLX bf16 or PyTorch CPU) and TimesFM 2.5 (MLX or CPU) behind a common wrapper (Darts has wrappers for both).
- Baselines: StatsForecast (naive, ETS, AutoARIMA), MLForecast/LightGBM, trend/carry rules.
- Evaluation: skfolio CombinatorialPurgedCV + WalkForward, custom DSR/PBO, scoringrules/properscoring-style CRPS and pinball implementations (not verified: choose a library at build time).
- Optional research: Kronos-base MLX (candle encoder / sampler), Toto 2.0 22M, TiRex-2 ONNX.
- Orchestration with Claude is the only cloud dependency; all forecast inference is local. Daily-bar forecasting for tens to hundreds of assets is lightweight enough for an M-series laptop even on CPU for the sub-250M models (inference of this scale on a MacBook is my estimate, not benchmarked).

---

## 8. Community findings (what practitioners report)

Reachability: Reddit (r/algotrading, r/MachineLearning, r/quant) was NOT reachable: `site:reddit.com` queries returned no Reddit pages and a direct fetch of Reddit's search JSON returned an HTML wall. X and Instagram were not reachable through the search tools (no results; I did not attempt logged-in access). YouTube: only a transcript-summary site surfaced a gold-trading Kronos video (https://sozai.app/transcript/ai-learned-12-billion-candles-trade-gold/); I did not see its results. Hacker News was reachable via the Algolia API.

What I found:
- HN, "Google's 200M-parameter time-series foundation model with 16k context" (2026-03-31, 327 points, 109 comments): https://news.ycombinator.com/item?id=47583045 . Representative comments: users note people "do use them to predict bitcoin prices intraday" and that these tools suit predictable series (insurance, demand), not Bitcoin; one commenter says they model trend/seasonality/residual rather than "egg prices"; skeptics doubt cross-domain pretraining helps financial data.
- HN, original TimesFM thread (2024-05-08, 317 points): https://news.ycombinator.com/item?id=40297946 . Standard efficient-markets pushback ("if stock prices were predictable by some technical means, they would be quickly driven to unpredictability"), alongside commenters arguing that LLM-style success motivates trying. Low information content on actual results.
- HN: Kronos paper submission (2026-10-10, 2 points, 0 comments): no discussion.
- Practitioner write-ups and repos (section 4.2, 4.5) are consistently negative on zero-shot direction and calibration, with the one mildly positive result being TimesFM as a filter on momentum (single-author blog, Sharpe 0.327 to 0.597).
- G-Research's NeurIPS 2025 review commentary (via a search snippet, unverified) says a generic foundation model is unlikely to beat their task-specific internal models: https://www.gresearch.com/news/neurips-paper-reviews-2025-2/
- Hype indicators: Kronos has 47.8k stars (more than Chronos at 6.3k) while the only independent tests I found are negative or inconclusive; marketing-style pages ("the secret AI model Wall Street doesn't want you to see") circulate. Stars here measure attention, not evidence.

---

## 9. Open questions

1. Daily vs intraday: does the user want daily swing signals or intraday? Evidence above is worst for intraday direction; the data and cost structure differ greatly.
2. Intraday data availability for realized variance (HAR needs it). Without it, range-based estimators from daily OHLC are the fallback; need data-track input.
3. Finance-pretrained TSFMs (FinText, from-scratch pretraining per Rahimikia et al.) are the one line of evidence with real gains; a local pretraining/fine-tuning run on the user's own data is feasible only for small models on a Mac. Worth a pilot? Needs a compute budget decision.
4. Metals (gold/silver futures or spot) and FX data quality and session conventions affect any seasonality or carry feature; carry requires rate/forward data (data track).
5. TimesFM 3.0 license: is paper trading with it "non-production"? Real-money use probably is not. Avoid until clarified by a lawyer; use 2.5.
6. TiRex community license terms and `arch` license were not verified here.
7. Exact Gu-Kelly-Xiu R^2 table values and the Rahimikia R^2 numbers should be checked against the full papers before they are quoted.
8. Last-commit dates for all repos (GitHub API was rate-limited; pages did not show dates). Check before adopting a dependency.
9. Whether to treat Moirai (CC BY-NC) and Kronos-large (closed) as out of scope; recommended yes for the first build.

---

## 10. Source index

Repos (stars as of 2026-11-14): https://github.com/google-research/timesfm ; https://github.com/amazon-science/chronos-forecasting ; https://github.com/shiyu-coder/Kronos ; https://github.com/SalesforceAIResearch/uni2ts ; https://github.com/time-series-foundation-models/lag-llama ; https://github.com/ibm-granite/granite-tsfm ; https://github.com/NX-AI/tirex ; https://github.com/NX-AI/tirex-2 ; https://github.com/DataDog/toto ; https://github.com/Time-MoE/Time-MoE ; https://github.com/thuml/Sundial ; https://github.com/unit8co/darts ; https://github.com/sktime/sktime ; https://github.com/Nixtla/statsforecast ; https://github.com/Nixtla/neuralforecast ; https://github.com/Nixtla/mlforecast ; https://github.com/bashtage/arch ; https://github.com/awslabs/gluonts ; https://github.com/sktime/pytorch-forecasting ; https://github.com/facebook/prophet ; https://github.com/skfolio/skfolio ; https://github.com/microsoft/qlib ; https://github.com/AI4Finance-Foundation/FinRL

Papers: arXiv 2611.12141, 2606.27100, 2511.18578, 2607.05291, 2604.00064, 2608.03259, 2609.04917, 2508.02739, 2605.20119 (Toto 2.0), 2510.15821 (Chronos-2), 2511.11698 (Moirai 2.0), 2607.01204 (TiRex-2); Gu-Kelly-Xiu https://www.nber.org/papers/w25398 ; Welch-Goyal https://www.nber.org/papers/w10483 ; Rossi 2013 https://econ-papers.upf.edu/papers/1369.pdf ; Hansen-Lunde https://econpapers.repec.org/RePEc:jae:japmet:v:20:y:2005:i:7:p:873-889 ; Corsi https://papers.ssrn.com/abstract=1365738 ; Moskowitz-Ooi-Pedersen https://papers.ssrn.com/abstract=2089463 ; Lustig-Roussanov-Verdelhan https://www.nber.org/papers/w14082.pdf ; Bailey-LdP DSR https://papers.ssrn.com/abstract=2460551 ; PBO https://papers.ssrn.com/abstract=2326253.

Other: Datadog Toto 2.0 blog https://www.datadoghq.com/blog/ai/toto-2/ ; Nixtla TimeGPT-2 https://www.nixtla.io/blog/timegpt-2-announcement ; HF model cards (chronos-2, Toto-2.0-313m, NX-AI/TiRex, ibm-granite TTM r2, FinText) as cited inline.
