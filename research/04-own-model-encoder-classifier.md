# Track 4: Own encoder + classifier on a "Profitability Index"

Research date: 2026-11-14. Constraint added mid-research: the project is LOCAL-FIRST (only Anthropic Claude may be a cloud model; training and inference of our own model run on the user's machine; Apple Silicon Mac assumed, not confirmed).

Conventions: "[seen]" = I read the page or API output this session. "[snippet]" = only seen in a search-result summary. "[memory]" = my own background knowledge, not re-verified. GitHub stars and dates were pulled with `gh api` on 2026-11-14 and are exact for that day.

---

## 1. TL;DR

1. "Profitability index" should not be one vague number. Formalize it as a **cost-aware, event-based, triple-barrier outcome**, and expose it as two heads on one model: (a) calibrated **P(take-profit before stop-loss, net of costs)**, which is a meta-label, and (b) **E[R_net]**, the expected net R-multiple. The scalar the rest of the system sees is `PI = E[R_net | x]`. The decision threshold is `p* = (1 + c) / (1 + b)`, with `b` = TP/SL ratio and `c` = round-trip cost in R units (derived in section 3).
2. **Start with gradient boosting (LightGBM) on hand-built features. Do not start with a deep encoder.** The evidence: tree models win on medium-sized tabular data ([Grinsztajn et al., NeurIPS 2022](https://arxiv.org/abs/2207.08815) [seen]); Qlib's own benchmark has LightGBM/XGBoost ahead of Transformer and TabNet on Alpha158 ([Qlib benchmarks](https://github.com/microsoft/qlib/tree/main/examples/benchmarks) [seen]); off-the-shelf time-series foundation models forecast daily excess returns poorly versus CatBoost/LightGBM ensembles ([Rahimikia et al., arXiv 2511.18578](https://arxiv.org/abs/2511.18578) [seen]).
3. An encoder only earns its place if it beats the GBM baseline under the same purged/CPCV protocol. The one real signal in favor of encoders: on Qlib's raw-ish Alpha360 inputs, GRU/LSTM/ALSTM (IC about 0.045 to 0.050) beat LightGBM (0.040). Small recurrent or conv encoders on raw sequences are viable candidates. Large Transformers were the worst there (IC 0.011). Frozen foundation-model embeddings (Chronos-2, Kronos) are a cheap experiment, not a bet.
4. "Progressive training" for a solo builder = **scheduled walk-forward retraining with champion/challenger and shadow deployment**, plus drift monitors that trigger early retrains. It is not online gradient updates. FreqAI, the closest open reference, labels its own `continual_learning` option "naive", experimental, and prone to overfitting ([FreqAI parameter table](https://www.freqtrade.io/en/stable/freqai-parameter-table/) [seen]).
5. Overfitting is the main enemy. Use purge + embargo, CPCV for model selection, Deflated Sharpe with an honest trial counter, label-permutation tests, and a hard rule that every experiment is logged (MLflow) so N is known.
6. RL (FinRL etc.) is the wrong first move. Maintained, popular, but the only independent live evidence I found is bad (PF 1.05 over 763 live trades, t-stat 0.55, with costs about 85x the simulation) and the FinRL authors themselves flag overfitting and the sim-to-real gap.
7. Everything here runs locally. A GBM trains in seconds to minutes on CPU. A 1M to 25M parameter encoder is feasible on MPS/MLX. Claude via API is useful only off the critical path (news-event labeling, text features, trade post-mortems).

---

## 2. Scope and assumptions

- Instruments: not fixed by the brief (crypto vs equities vs FX). Bar frequency also open. Where it matters (window lengths, cost model) I give both daily and intraday notes.
- This model is component (4) of the system. It consumes market data (2), optionally forecasts (3) and LLM/news features (1), and emits a score to risk/asset management (5) and execution (6). Everything below assumes the score is a probability/expectation, not an order.
- Hardware assumed: Apple Silicon Mac with unified memory (16 GB or more). Flagged as an assumption.

---

## 3. "Profitability index": formalization options

Setup common to all options (López de Prado, *Advances in Financial Machine Learning*, ch. 3 [memory]; implementations in section 9):

- **Events**, not every bar: sample candidate entry times with a CUSUM filter or a volatility-breakout rule, so labels are less redundant.
- For each event at time `t`, side `s` (from a primary rule, or evaluate both sides), volatility estimate `σ_t` (EWMA).
- Barriers: take-profit at `+k_tp·σ_t`, stop-loss at `-k_sl·σ_t`, vertical barrier at `t+h` bars.
- Outcome net of costs: fees + half-spread + modelled slippage + funding/borrow where relevant. Express PnL in **R** units (R = SL distance), so `R_net ∈ [-(1+c), b-c]` for barrier exits, and a fractional value on timeout.

### Options

| # | Target | Definition | Pros | Cons | Fits |
|---|---|---|---|---|---|
| A | **3-class triple-barrier** | y ∈ {-1, 0, +1}: which barrier first (0 = timeout) | The classic, widely documented, ignores nothing about path | Class 0 is ambiguous; ignores magnitude and costs unless folded in; barrier params arbitrary | Baseline, research parity with literature |
| B | **Binary meta-label ("take/skip")** | Given a side from a primary rule, y=1 if net R > 0 (or TP hit first net of cost) | Focuses on precision; model outputs a probability you can calibrate and threshold; easy to size from p | Needs a primary signal; evidence that it adds value is mixed (below); loses magnitude | Gate on rule-based or agent-generated trade ideas |
| C | **Expected-R regression** | y = R_net (barrier-clipped, so heavy tails are bounded) | Directly the quantity risk/sizing needs; one number | Noisier to fit; needs calibration checks on bucketed predictions | Sizing and ranking |
| D | **Forward risk-adjusted return bucket** | Fixed-horizon return / ex-ante vol, cut into quantiles or cross-sectional ranks | Natural for cross-sectional ranking (Qlib-style IC/RankIC); no barrier params | Ignores path and stops; overlapping labels; no trade-management semantics | Universe ranking, multi-asset selection |
| E | **P(TP before SL) with asymmetric barriers, after costs** | Option B with explicit `b` and `c`; decision threshold `p* = (1+c)/(1+b)` | Gives an interpretable breakeven; ties the model to the cost model | Same as B | The decision rule for B |

Derivation for E: EV per trade in R units = `p·(b−c) − (1−p)·(1+c) = p·(1+b) − (1+c)`. So EV>0 iff `p > (1+c)/(1+b)`. Example: b=2, c=0.1 gives p* = 1.1/3 = 0.367. Note that this is the model-free breakeven. The classifier's calibrated p must clear it by a margin that covers estimation error.

### Evidence on meta-labeling (mixed, thin)

- Origin: AFML (López de Prado). Formal treatment: Joubert, "Meta-Labeling: Theory and Framework", *J. Financial Data Science* 4(3), 2022 [snippet], with a follow-up on calibration and position sizing (Meyer, Barziy, Joubert, 2023) [snippet]. I could not open either full text.
- Positive: Hudson & Thames report event sampling + triple barrier + meta-labeling improves strategy performance ([H&T research update](https://hudsonthames.org/?p=3448) [snippet], vendor source). A DEV post on a LightGBM FreqAI plugin says switching to triple-barrier labels was its biggest single improvement ([DEV post](https://dev.to/stefano_viana_dda882cfae5/how-i-built-a-profitable-freqai-plugin-using-institutional-ml-techniques-1l9k) [snippet], anecdote, no methodology).
- Negative/skeptical: QuantConnect thread "Why Meta-Labeling Is Not a Silver Bullet" ([link](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/) [seen]). Author's grid search over several seeds: meta-model widened the result range but lowered mean Sharpe. One reply saw it hurt an ExtraTrees strategy and suspected their own leakage. A Brazilian bachelor's thesis (MACD primary with RF/XGB/logistic secondary) found no expressive performance ([Insper repository](https://repositorio.insper.edu.br/entities/publication/14261761-ee4f-4466-91e4-771dd445f258/full) [snippet]). A 2023 Lund thesis reported significant skill for an equity market-neutral strategy ([Lund](https://lup.lub.lu.se/student-papers/search/publication/9120301) [snippet]).
- My reading: a meta-model cannot extract information that is not in its features. It helps most when the primary signal is high-recall/low-precision and the secondary model sees features the primary ignores (regime, volatility state, news/text, cross-asset context). Treat "meta-labeling adds value" as a hypothesis to test per strategy, not a given.

### Recommendation

Build one model with **two heads over a shared representation**:

1. `p̂ = P(R_net > 0)` (binary, calibrated via isotonic/Platt on a purged calibration fold).
2. `Ê = E[R_net]` (regression on barrier-clipped R).

Publish `PI = Ê` as the scalar and `p̂` as the confidence. Gate trades with `p̂ > p* + margin` and `Ê > 0`. Test option D (cross-sectional rank) only if the universe is a basket where ranking matters. Keep option A as a literature-parity benchmark. Version the label spec (k_tp, k_sl, h, cost model, event sampler) as a hashed config so every model is traceable to its label definition.

Cost-aware labeling note: costs must be part of the label, not subtracted afterwards, otherwise the model learns edges smaller than costs. Use a conservative cost model, and given the live evidence below (execution costs about 85x higher than simulated in one author's PPO study, [MQL5 forum](https://www.mql5.com/en/forum/519231) [seen]), stress the labels at 2x costs and require the edge to survive.

### Sample weights and sampling hygiene

Overlapping barrier windows make labels non-IID. Standard AFML fixes [memory]: weight by average uniqueness (concurrency), weight by absolute return attribution, optional time-decay, and use sequential bootstrap for bagged learners. FreqAI's analogue is `weight_factor` (exponential recency weights) ([feature engineering docs](https://www.freqtrade.io/en/stable/freqai-feature-engineering/) [seen]). Libraries with `sample_weights` modules: mlfinpy, finmlkit (section 9).

### Fractional differentiation

Intended to keep memory while achieving stationarity [memory]. I found no independent out-of-sample evidence that it beats plain returns plus vol-normalized features. The `fracdiff` package (340 stars, last push 2023-12-16, BSD-3, [repo](https://github.com/fracdiff/fracdiff) [seen via gh]) is stale. Treat as optional feature experiment, low priority.

---

## 4. Encoder options

Key: Local cost estimates are my arithmetic (fp32 = 4 bytes/param; Adam training state about 4x weights before activations), not measurements. Sequence lengths/batch sizes matter more than parameter count for activation memory.

| Option | What it is | Evidence on financial data | Local feasibility | Verdict |
|---|---|---|---|---|
| **LightGBM/XGBoost/CatBoost on engineered features** (not an encoder, the baseline) | Trees on returns, vol, microstructure, regime features | Qlib CSI300 Alpha158: XGBoost IC 0.0498, LightGBM 0.0448, CatBoost 0.0481 vs Transformer 0.0264, TabNet 0.0204 ([Qlib](https://github.com/microsoft/qlib/tree/main/examples/benchmarks) [seen]). Trees win at ~10K samples ([Grinsztajn](https://arxiv.org/abs/2207.08815) [seen]). GBDT with dropout robust to regime change ([Wong & Barahona](https://arxiv.org/abs/2301.00790) [seen]) | CPU, seconds to minutes | **Primary model from day 1** |
| **Linear / DLinear** | One-layer linear heads with trend decomposition | Beats elaborate Transformers on long-horizon forecasting benchmarks ([Zeng et al.](https://arxiv.org/abs/2205.13504) [seen]); not a finance paper | Trivial | **Mandatory sanity baseline for any encoder** |
| **Small GRU/LSTM/ALSTM** on raw windows | 1 to 2 layer recurrent encoder | Qlib Alpha360: GRU IC 0.0493, LSTM 0.0448, ALSTM 0.0497 vs LightGBM 0.0400 ([Qlib](https://github.com/microsoft/qlib/tree/main/examples/benchmarks) [seen]) | <1M params; CPU/MPS fine | **First encoder candidate** |
| **Small TCN / 1D-CNN** | Dilated causal conv stack | No finance-specific source verified this session | Cheap | Good candidate alongside GRU [memory-based reasoning, untested] |
| **MiniRocket/MultiRocket features + linear/GBM** | Random conv kernels, no training | In a vendor benchmark on 33 UCR/UEA datasets, convolutional MiniRocket/MultiRocket ranked ahead of Chronos-2 under a frozen-probe protocol ([AIMultiple](https://aimultiple.com/time-series-classification) [snippet], vendor blog). Not finance data. Library: [aeon](https://github.com/aeon-toolkit/aeon) 1,479 stars, BSD-3, pushed 2026-11-13 [seen via gh] | CPU | Cheap "encoder-like" feature baseline worth a day |
| **PatchTST** (patching + channel independence, masked-patch SSL) | [arXiv 2211.14730](https://arxiv.org/abs/2211.14730), ICLR 2023. Repo [yuqinie98/PatchTST](https://github.com/yuqinie98/PatchTST): 2,748 stars, last push 2024-08-12, Apache-2.0 [seen via gh] | Strong on forecasting benchmarks; SSL pretraining claims are on ETT-style data, not noisy returns. In a 5-stock study, PatchTST was one of the from-scratch models trained against pretrained TSFMs, which won 8 of 10 comparisons but with gains over random walk "small and sparse" ([arXiv 2606.27100](https://arxiv.org/abs/2606.27100) [seen]) | 1M to 10M params feasible on MPS | Candidate only after GRU/CNN; repo is quiet since 2024 |
| **TS2Vec** (hierarchical contrastive) | [arXiv 2106.10466](https://arxiv.org/abs/2106.10466) [snippet]; repo [zhihanyue/ts2vec](https://github.com/zhihanyue/ts2vec) 884 stars, last push 2024-07-29, MIT [seen via gh] | Strong on UCR/UEA classification [snippet]; no financial-data validation found | Small conv encoder, local OK | Reasonable for an SSL pretraining experiment; unproven on returns |
| **TimesNet** (Time-Series-Library) | 2D-variation conv backbone; library [thuml/Time-Series-Library](https://github.com/thuml/Time-Series-Library) 13,079 stars, last push 2026-04-18, MIT [seen via gh] | Paper details not re-verified [memory]; no finance-specific evidence found | Heavier; feasible but low expected gain | Skip initially |
| **Frozen foundation-model embeddings: Chronos-2** | 120M-param encoder-only, Apache-2.0, 8,192 context, released 2025-10-20 [snippet]; small variant 28M [snippet]; repo [amazon-science/chronos-forecasting](https://github.com/amazon-science/chronos-forecasting) 6,301 stars, pushed 2026-10-05, Apache-2.0 [seen via gh] | Off-the-shelf TSFMs forecast daily excess returns poorly vs CatBoost/LightGBM ([2511.18578](https://arxiv.org/abs/2511.18578) [seen]); pretraining from scratch on financial data helped. Contradictory: [2606.27100](https://arxiv.org/abs/2606.27100) [seen] finds pretrained TSFMs win 8 of 10 vs from-scratch nets on 5 US equities but gains vs random walk are small and statistically significant in only 2 cases; "not reliable engines for significant alpha". Frozen Chronos-2 for classification generally trails fine-tuned models and conv baselines ([e-nose study](https://arxiv.org/pdf/2606.27672) [snippet]) | ~480 MB fp32 weights; inference local on MPS/CPU | Cheap to try as extra features; low prior |
| **Kronos** (finance-specific decoder, K-line tokenizer) | [arXiv 2508.02739](https://arxiv.org/abs/2508.02739), AAAI 2026. Repo [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos): 47,771 stars, last push 2026-04-13, MIT [seen via gh]. Sizes: mini 4.1M, small 24.7M, base 102.3M open; large 499.2M closed [seen, README] | Authors claim RankIC +93% over leading TSFM zero-shot [snippet, authors' own claim]. README warns its Qlib fine-tune demo is simplified and ignores costs, slippage and risk [seen]. README documents `KronosPredictor` only, not a standalone encoder API, so extracting embeddings requires reading code | mini/small are very local-friendly | Good candidate for frozen-feature test; do not trust its headline numbers without our own CPCV |
| **TimesFM** | [google-research/timesfm](https://github.com/google-research/timesfm) 35,470 stars, pushed 2026-11-13, Apache-2.0 [seen via gh] | See TSFM finance papers above | Local feasible; parameter count not verified | Same status as Chronos-2 |
| **Text fusion: FinBERT / sentence embeddings** | [ProsusAI/finBERT](https://github.com/ProsusAI/finBERT): 2,280 stars, last push 2026-10-12, Apache-2.0 [seen via gh] | No controlled evidence gathered this session that text embeddings add OOS alpha beyond price features | FinBERT (about 110M, BERT-base) inference runs locally; embed headlines offline, join point-in-time | Add late, as meta-model features; keep strictly point-in-time |
| **Cross-asset tokens** | Treat each asset-window as a token in one sequence | No financial evidence found. FreqAI's cheaper equivalent: `include_corr_pairlist` adds correlated-pair features ([docs](https://www.freqtrade.io/en/stable/freqai-feature-engineering/) [seen]) | | Do as tabular features first (BTC/ETH/SPY/VIX context), tokens later |

Which help vs overfit, in one paragraph: the verified record says (i) simple models and GBMs are hard to beat on noisy finance panels, (ii) Transformers and TabNet were the worst in Qlib's tables (Alpha360: Transformer IC 0.0114, TabNet 0.0099), (iii) zero-shot foundation models have at best marginal, statistically fragile edge on returns, (iv) in-domain pretraining on financial data is the version that helped in the one study that tested it, and (v) recurrent/conv encoders on raw windows are competitive. Note these are mostly daily-frequency, cross-sectional equity results (Qlib CSI300), which may not transfer to the user's market.

Practical plan for the encoder: **small GRU/TCN (0.1M to 2M params) with the two heads, trained supervised on the same labels**, optionally initialized by masked-reconstruction SSL on a larger unlabeled history. Judge it only by incremental lift over LightGBM and over LightGBM + frozen-embedding features. If the encoder's embeddings are fed to LightGBM instead of the heads, you keep GBM robustness.

---

## 5. Progressive training: concrete design

### 5.1 Options compared

| Approach | Description | Risks | Solo-builder fit |
|---|---|---|---|
| Static model | Train once | Decay under regime change | Baseline only |
| **Scheduled walk-forward retrain** | Refit on a sliding or expanding window every N days; evaluate next block | Compute cost; window choice | **Recommended** |
| Continual / warm-start fine-tuning | Initialize new model from last checkpoint | FreqAI: naive, prone to overfitting, can stall in local minima; disables PCA ([FreqAI running](https://www.freqtrade.io/en/stable/freqai-running/) [seen]). Catastrophic forgetting if you train only on recent data | Experimental, behind a flag |
| True online learning (River etc.) | Per-sample updates | Hard to validate; label delay (barrier outcomes arrive after `h` bars) | Use River for *monitoring* (drift), not as the main learner |
| Regime-conditioned models | One model per regime | Regime labels are themselves fitted; sample splits shrink | Start with regime *features*, not separate models |

Evidence on window schedules: no verified source settles rolling vs expanding. FreqAI uses a fixed sliding window plus optional recency weighting; in its docs the window (`train_period_days`) and retrain cadence (`live_retrain_hours`, `backtest_period_days`) are first-class hyperparameters ([parameter table](https://www.freqtrade.io/en/stable/freqai-parameter-table/) [seen]). Treat window type, window length and cadence as hyperparameters to be tuned under the walk-forward harness and counted as trials. A 2023 paper on temporal tabular data with regime changes found that **post-prediction** adaptation (dynamic feature projection, dynamic model ensembling by recent performance) improved Sharpe/Calmar *without retraining* ([Wong & Barahona](https://arxiv.org/abs/2301.00790) [seen]). That is a cheap, solo-friendly alternative to continual learning.

### 5.2 FreqAI as the reference architecture (studied and summarized)

Sources: [FreqAI intro](https://www.freqtrade.io/en/stable/freqai/), [running](https://www.freqtrade.io/en/stable/freqai-running/), [developers](https://www.freqtrade.io/en/stable/freqai-developers/), [feature engineering](https://www.freqtrade.io/en/stable/freqai-feature-engineering/), [parameter table](https://www.freqtrade.io/en/stable/freqai-parameter-table/), [JOSS paper](https://joss.theoj.org/papers/10.21105/joss.04864) (Caulk, Törnquist et al., JOSS 7(80), published 2022-12-15) [all seen]. Freqtrade repo: 56,864 stars, last push 2026-11-12, GPL-3.0 [seen via gh]. Note GPL-3.0: borrow ideas, do not copy code into a non-GPL project.

Design points worth borrowing:

- **Three objects**: `IFreqaiModel` (persistent: data collection, training, inference), `FreqaiDataKitchen` (non-persistent, one per asset/model pair), `FreqaiDataDrawer` (persistent store of predictions and model locations).
- **Sliding-window retraining**: train on `train_period_days`; in backtests, predict `backtest_period_days`, slide forward, retrain. A timerange of 8 weeks with 7-day windows trains 8 models. In live, retraining runs on a background thread, newest model kept in RAM for inference, and predictions always use the newest *completed* model. Pairs are queued so all models stay roughly equally fresh.
- **Staleness guard**: `expiration_hours` blocks predictions from models older than N hours (default 0 = never expire). `live_retrain_hours` is the minimum wait between retrains (default 0 = as often as possible). **Borrow: a model-age kill switch.**
- **Crash resilience / model registry in miniature**: each trained model saved in `sub-train-*_TIMESTAMP/` with metadata JSON (normalization ranges, feature list), model file, PCA/SVM objects, and training data frames (used later for the dissimilarity index); `pair_dictionary.json` tracks the training queue and latest model; `identifier` namespaces a run and reusing it resumes; `purge_old_models` keeps N (default 2).
- **Label discipline**: `set_freqai_targets()` runs once per backtest window to mimic live; feature engineering runs once over the full range, so features must avoid lookahead (their docs say this explicitly). Labels like `label_period_candles` look ahead by design.
- **Prediction-time safety nets**: Dissimilarity Index (`DI_threshold`) refuses to predict on points far from training data; optional SVM and DBSCAN outlier removal; `noise_standard_deviation` adds Gaussian noise to features; `weight_factor` recency weights; PCA optional. **Borrow: refuse-to-predict when inputs are out-of-distribution.**
- **Normalization stored with the model** (MinMaxScaler(-1,1) + VarianceThreshold by default), so inference reproduces training preprocessing.
- **`continual_learning`** (default False): next model starts from the previous model's final state. Docs: "naive", experimental, prone to overfitting.
- **Weaknesses to avoid** (partly my inference): the example `data_split_parameters` uses a plain `test_size` split (0.25 in the docs' example) with no stated purge/embargo for overlapping labels; no champion/challenger gate (the newest model is always used, not the best); no built-in multiple-testing correction. We should add all three.

### 5.3 Proposed pipeline (local)

```
 data snapshot (DVC-tracked parquet, point-in-time, includes delistings/halts)
   -> event sampler (CUSUM / vol breakout)           [label_spec hash]
   -> triple-barrier labels, cost-aware, R units
   -> uniqueness weights, time-decay weights
   -> features (price/vol/microstructure/cross-asset/regime/text-embeds), all as-of t
   -> TRAIN WINDOW [t0, T-embargo]  |  CALIB fold (purged)  |  embargo  |  TEST block [T, T+Δ]
   -> candidate models: LightGBM (champion family), small GRU/TCN heads, ensemble
   -> calibration (isotonic) + threshold from p* + margin
   -> metrics: log-loss, Brier, calibration curve, hit-rate@threshold, mean R_net, PSR/DSR
   -> registry (MLflow): params, label_spec hash, data hash, metrics, trial counter
   -> CHAMPION vs CHALLENGER gate
        challenger -> shadow mode (scores logged, no orders) for >= M days / >= K events
        promote iff beats champion on shadow window + passes sanity (no drift alarms,
                    calibration error < x, DSR > 0 given N trials)
   -> serve champion (model-age kill switch, OOD refuse-to-predict)
   -> monitors: ADWIN/Page-Hinkley on rolling realised-vs-predicted (hit-rate error,
                Brier), PSI/KS on top features -> triggers early retrain or demotion
```

Schedule defaults (starting points to be tuned, not evidence-based): retrain weekly for daily-bar strategies using an expanding window with exponential recency weights; for intraday/crypto try a sliding window of 3 to 12 months and daily retrain. Always keep the previous champion as fallback and as a live benchmark.

Replay/forgetting: when warm-starting an encoder, mix recent data with a replay sample from older regimes (stratified by volatility regime), at low learning rate. Gate this behind the same champion/challenger test. If it does not beat a from-scratch refit on shadow data, delete it.

Drift detection: River ([online-ml/river](https://github.com/online-ml/river): 6,148 stars, last push 2026-11-13, BSD-3 [seen via gh]) implements ADWIN and Page-Hinkley [memory; River's own docs not opened]. ADWIN is described as a sliding window that grows until drift is detected, with confidence parameter delta (default 0.002 in Menelaus' implementation [snippet](https://menelaus.readthedocs.io/en/latest/menelaus.change_detection.html)). Monitor model *error stream* (not just inputs), because input drift does not imply edge loss.

Qlib has an analogous but heavier stack: `OnlineManager`/`OnlineStrategy`/`OnlineTool`/`Updater` for online serving and rolling retrain scripts, plus DDG-DA for concept drift ([Qlib online docs](https://qlib.readthedocs.io/en/latest/component/online.html) [snippet]). Qlib: 50,272 stars, last push 2026-11-04, MIT, latest release v0.9.8 (2026-10-08) [seen via gh]. Good for ideas; heavy for a crypto/FX single-asset system and centered on A-share/US daily data.

---

## 6. Overfitting defenses

| Defense | What it is | Evidence / source | Notes |
|---|---|---|---|
| **Purged + embargoed K-fold** | Remove training samples whose label windows overlap test; embargo after test | AFML ch. 7 [memory]. Implemented in mlfinpy, skfolio, purged-cross-validation (section 9) | Needed because barrier labels span `h` bars |
| **CPCV** | Combinatorial purged CV: many train/test combinations produce multiple backtest paths | skfolio `CombinatorialPurgedCV` with `n_folds`, `n_test_folds`, `purged_size`, `embargo_size`, `n_test_paths` ([docs](https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html) [seen]). Arian, Norouzi, Seco (*Knowledge-Based Systems*, 2024, [DOI 10.1016/j.knosys.2024.112477](https://doi.org/10.1016/j.knosys.2024.112477)) found CPCV gave lower PBO and higher DSR statistic than other methods, with walk-forward worst at preventing false discoveries ([snippet](https://bohrium.dp.tech/paper/arxiv/324dfd175c19894198c6e870b5d6427eec1a3ff441baa75b0dbd5e856e73e5f8)) | Caveat: **synthetic data only** (Heston, Merton, drift-burst, regime switching); not replicated on real data as far as I found |
| **Deflated Sharpe Ratio** | Adjusts Sharpe for number of trials, skew, kurtosis | Bailey & López de Prado, *J. Portfolio Management* 40(5), 2014 ([SSRN 2460551](https://papers.ssrn.com/abstract=2460551) [seen via search]) | Needs an **honest N**: count every config you ever tried (MLflow run count) |
| **PBO** | Probability of backtest overfitting via combinatorial IS/OOS ranking | Bailey, Borwein, López de Prado, Zhu [memory]. Implementation: [esvhd/pypbo](https://github.com/esvhd/pypbo) 145 stars, pushed 2026-07-06, AGPL-3.0 [seen via gh] (AGPL: use as a tool, mind licensing if embedding) | |
| **Multiple-testing arithmetic** | Repeated walk-forward on same data inflates false discoveries | One summary of López de Prado: 20 walk-forward backtests on the same data likely yield one false discovery at nominal 95% ([CXO Advisory](https://www.cxoadvisory.com/big-ideas/10-steps-to-becoming-a-better-quant) [snippet]); paper [10 Reasons Most ML Funds Fail](https://www.garp.org/white-paper/the-10-reasons-most-machine-learning-funds-fail) [snippet] | Hold out a final untouched period and open it once |
| **Label-permutation / random-feature controls** | Shuffle labels or add noise features; the model must lose | Standard; not sourced | Cheap, catches pipeline leakage |
| **Small capacity + regularization** | Shallow trees, colsample, dropout GBDT (`dart`), early stopping, weight decay | Wong & Barahona: GBDT with dropout robust and cheap ([arXiv 2301.00790](https://arxiv.org/abs/2301.00790) [seen]). Numerai's example model uses colsample_bytree=0.1 ([forum](https://forum.numer.ai/t/feature-neutralization-workflow/1059) [snippet]) | |
| **Noise-robust training** | Gaussian input noise, label smoothing, bagging across seeds | FreqAI `noise_standard_deviation` (default 0) [seen]; the rest is standard practice | |
| **MDA / feature-importance hygiene** | Permutation importance on purged OOS folds, not in-sample gain | AFML ch. 8 [memory]. Anecdote: SHAP pruning 200 to 30 features raised OOS accuracy 3% ([DEV](https://dev.to/stefano_viana_dda882cfae5/how-i-built-a-profitable-freqai-plugin-using-institutional-ml-techniques-1l9k) [snippet], anecdote) | Never select features on the test fold |
| **Era-wise validation** | Group by time eras, hold out whole eras | Numerai practice: tune by era-grouped CV, use validation only as a sanity check ([forum](https://forum.numer.ai/t/feature-neutralization-workflow/1059) [snippet]) | Era boosting and neutralization are debated; do not adopt untested |
| **Live gap discipline** | Paper-trade the exact code | Look-ahead and data-pipeline bugs surface here; a Quantopian study of 888 algorithms found backtest Sharpe told almost nothing about live ([snippet via search](https://www.techinterview.org/post/3233477314/why-backtest-sharpe-collapses-live/?format=md), secondary) | Shadow mode in the pipeline is exactly this |

Gu, Kelly & Xiu ([*Review of Financial Studies* 2020](https://nber.org/papers/w25398)) is the standard academic evidence that ML adds value in asset pricing: trees and neural nets did best because they capture nonlinear interactions, and all methods agreed on momentum, liquidity and volatility signals [seen via search snippet]. A thesis could not replicate the NN gains on a reduced dataset ([Erasmus thesis](https://thesis.eur.nl/pub/59944/513098rh-thesis.pdf) [snippet]). That study is monthly US equities, not intraday or crypto.

---

## 7. Baselines to beat (gate before any deep encoder)

Every candidate must beat all of these under identical splits, labels, costs:

1. **Do nothing / buy-and-hold** and **primary rule taking every signal** (if using meta-labeling, the meta-model must beat "take all").
2. **Random-label permutation**: shuffled labels must give ~chance log-loss and zero edge. If not, there is leakage.
3. **Logistic regression** on 5 to 10 features (vol, momentum, range, time-of-day).
4. **DLinear/naive** sequence baseline.
5. **LightGBM / XGBoost** on the full engineered feature set (the real bar). Qlib has XGBoost IC 0.0498 vs LightGBM 0.0448 vs CatBoost 0.0481 on Alpha158, so try all three.
6. **GBM + frozen foundation-model embedding features** (tests whether the foundation model adds anything).

Go criteria, suggested: encoder (or ensemble) improves OOS mean R_net or DSR over best GBM by more than the run-to-run seed noise, over at least 3 CPCV paths, and survives 2x cost stress.

Qlib seeds lesson: its table reports mean±std over 20 seeds, so any comparison here should too (neural nets especially).

---

## 8. RL alternative

| Project | Stars | Last push | License | Notes |
|---|---|---|---|---|
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 17,068 | 2026-11-03 | MIT | DRL framework; paper [arXiv 2111.09395](https://ar5iv.labs.arxiv.org/html/2111.09395); authors acknowledge the sim-to-real gap and use rolling retraining |
| [FinRL-Meta](https://github.com/AI4Finance-Foundation/FinRL-Meta) | 1,964 | 2026-10-12 | MIT | Benchmarks/environments; [paper](https://arxiv.org/pdf/2211.03107): low signal-to-noise, survivorship bias, backtest overfitting named as core obstacles [snippet] |
| [Stable-Baselines3](https://github.com/DLR-RM/stable-baselines3) | 14,010 | 2026-10-26 | MIT | General RL library underneath most trading envs |
| Qlib (RL component) | see section 5 | | | RL module exists in docs, not the main use case |

(All figures [seen via gh].) Community/independent evidence:

- HN thread on an A3C trading paper (2020-04-29, 288 points / 135 comments, [link](https://news.ycombinator.com/item?id=23022864) [seen]): top skeptical comments say backtests ignore latency/slippage/fees, are easy to overfit, and that the strategy must articulate which market inefficiency it exploits. Several self-identified HFT/hedge-fund quants. One commenter pointed out the paper assumed a fixed 20-ruble commission and no buy-and-hold comparison.
- PPO on gold (MQL5): in the author's earlier work, 763 live demo trades gave profit factor 1.05, t-stat 0.55 ("indistinguishable from zero"); execution costs about 85x higher than simulation; outcome-weighted behavioural cloning pushed the policy toward Hold (48% to 82%), with 12 final models trading not at all ([MQL5 forum discussion](https://www.mql5.com/en/forum/519231) [seen]). Single author, forex/gold, but a rare live-versus-sim record.
- Gort et al. (ICAIF 2022) argue earlier DRL crypto papers had inflated backtests and propose a hypothesis-test approach with combinatorial CV to reject overfit agents ([arXiv 2209.05559](https://arxiv.org/abs/2209.05559) [snippet]).
- A 2026 Research Square preprint on PPO portfolio allocation argues for multi-seed evaluation, matched costs and classical baselines before claiming outperformance ([preprint](https://assets-eu.researchsquare.com/files/rs-9824202/v1_covered_2dbf3593-a58c-4edb-bb2a-bb85e54443cb.pdf) [snippet], unreviewed).
- I did not find a dedicated independent audit of FinRL results. "Usually disappointing live" is consistent with the evidence I could verify but is not proven by a large independent sample.

Verdict: keep RL out of the critical path. RL's one conceptual advantage (optimizing the trade-management policy directly) can be approximated here by learning calibrated p̂ and Ê and letting the risk module (track 5) choose sizing.

---

## 9. Repositories and tooling (all stats pulled 2026-11-14 via `gh api`)

### Labeling / AFML tooling

| Repo | Stars | Last push | License | Notes |
|---|---|---|---|---|
| [hudson-and-thames/mlfinlab](https://github.com/hudson-and-thames/mlfinlab) | 4,973 | 2023-10-02 | NOASSERTION | Now closed-source; public repo exists only for issues, per its README [seen]. Do not depend on it |
| [baobach/mlfinpy](https://github.com/baobach/mlfinpy) | 92 | 2026-10-11 | MIT | Open "from the ground up" alternative inspired by MlFinLab [seen README]. Modules seen: `labeling` (triple-barrier/meta-label, trend scanning, fixed horizon, raw return), `sample_weights`, `sampling`, `cross_validation` (incl. `combinatorial.py`), `bet_sizing`, `structural_breaks`, `data_structure`, `ensemble`, `filters`. Latest release tag 0.1.2 (2024-10-09) |
| [terbed/finmlkit](https://github.com/terbed/finmlkit) | 114 | 2026-10-25 | MIT | Numba-based; bars (time/tick/volume/dollar/CUSUM/imbalance/run), triple-barrier with meta-labeling, sample weights (concurrency, return attribution, class imbalance), FeatureKit. README claims ~60x faster bar aggregation than pandas and 600x over MLFinPy (author's claim, unverified). Latest release v0.1.11 (2025-09-10) |
| [eslazarev/purged-cross-validation](https://github.com/eslazarev/purged-cross-validation) | 64 | 2026-11-13 | MIT | sklearn-compatible purging, embargo, CPCV, deflated Sharpe |
| [skfolio/skfolio](https://github.com/skfolio/skfolio) | 2,637 | 2026-11-13 | BSD-3 | Portfolio optimization library with `CombinatorialPurgedCV` (docs seen) |
| [esvhd/pypbo](https://github.com/esvhd/pypbo) | 145 | 2026-07-06 | AGPL-3.0 | PBO/DSR |
| [fracdiff/fracdiff](https://github.com/fracdiff/fracdiff) | 340 | 2023-12-16 | BSD-3 | Stale |
| [aeon-toolkit/aeon](https://github.com/aeon-toolkit/aeon) | 1,479 | 2026-11-13 | BSD-3 | Rocket-family transforms |

Searches for "afml port" and similar returned nothing notable by stars. The maintained choices are mlfinpy and finmlkit, both small projects with few maintainers; assume you will read and test their code, and consider vendoring the 200 lines you need (triple-barrier + uniqueness weights + purged CV are short).

### Frameworks that "train a model to score trades"

| Repo | Stars | Last push | License | What to borrow |
|---|---|---|---|---|
| [freqtrade](https://github.com/freqtrade/freqtrade) (FreqAI) | 56,864 | 2026-11-12 | GPL-3.0 | Sliding-window retrain, model expiry, DI outlier refusal, crash-safe model store (section 5.2) |
| [microsoft/qlib](https://github.com/microsoft/qlib) | 50,272 | 2026-11-04 | MIT | Model zoo + benchmark tables, `Recorder` experiment tracking, OnlineManager, rolling retrain, DDG-DA |
| [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) | 15,367 | 2026-10-21 | MIT | LLM-driven factor/model R&D loop (relevant to track 1 agents; I did not study it in depth) |
| [jesse-ai/jesse](https://github.com/jesse-ai/jesse) | 8,803 | 2026-11-10 | MIT | Has ML docs on meta-labeling and multiclass labels ([docs](https://docs.jesse.trade/docs/research/ml/meta-labeling) [snippet, not opened]) |
| [edtechre/pybroker](https://github.com/edtechre/pybroker) | 3,712 | 2026-11-09 | NOASSERTION | Walk-forward ML backtesting in Python; [Show HN 2023](https://news.ycombinator.com/item?id=35084227) (70 points) |
| Kaggle Jane Street 2020-21 | n/a | n/a | n/a | Top solution reportedly XGBoost + supervised-autoencoder MLP ensemble ([blog](https://asterblogs.netlify.app/jane-street-ml) [snippet], detail unverified); lesson is ensemble of GBM and a small regularized NN, with time-aware CV |
| Numerai | n/a | n/a | n/a | Era-grouped CV; GBM with low colsample; skepticism on neutralization ([forum](https://forum.numer.ai/t/feature-neutralization-workflow/1059)) |

### Foundation models and training stack

| Repo | Stars | Last push | License |
|---|---|---|---|
| [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) | 47,771 | 2026-04-13 | MIT |
| [google-research/timesfm](https://github.com/google-research/timesfm) | 35,470 | 2026-11-13 | Apache-2.0 |
| [amazon-science/chronos-forecasting](https://github.com/amazon-science/chronos-forecasting) | 6,301 | 2026-10-05 | Apache-2.0 |
| [ml-explore/mlx](https://github.com/ml-explore/mlx) | 29,156 | 2026-11-13 | MIT |
| [microsoft/LightGBM](https://github.com/microsoft/LightGBM) | 18,977 | 2026-11-12 | MIT |
| [mlflow/mlflow](https://github.com/mlflow/mlflow) | 28,800 | 2026-11-14 | Apache-2.0 (latest v3.18.0, 2026-11-04) |
| [iterative/dvc](https://github.com/iterative/dvc) | 15,973 | 2026-11-09 | Apache-2.0 |
| [optuna/optuna](https://github.com/optuna/optuna) | 15,043 | 2026-11-13 | MIT |
| [wandb/wandb](https://github.com/wandb/wandb) | 11,319 | 2026-11-14 | MIT (client; service is SaaS, so excluded by the local-first rule) |

---

## 10. Local-first stack (new section, per coordinator constraint)

### 10.1 Principles

- Training and inference of our own model never calls a cloud API. Only Claude via Anthropic API is permitted off-box, and only **off the critical path** (section 10.5).
- Assumption: Apple Silicon Mac. Unified memory means no VRAM wall; the practical limit is system RAM (16 GB or more recommended).

### 10.2 Sizing and feasibility (estimates are my arithmetic unless cited)

| Model | Params | fp32 weights | Training memory (Adam, weights+grads+2 moments, before activations) | Feasibility |
|---|---|---|---|---|
| LightGBM/XGBoost | n/a | n/a | MBs for ~10^5 to 10^6 rows × 100 to 500 features | CPU; seconds to minutes per fit; whole CPCV sweep in minutes to hours. Not measured here |
| GRU/TCN heads | 0.1M to 2M | <10 MB | <50 MB | CPU or MPS; minutes per fit on 10^5 sequences. Not measured |
| PatchTST/TS2Vec-sized | 1M to 25M | 4 to 100 MB | up to ~400 MB | MPS/MLX feasible; hours for an SSL pretrain, my estimate |
| Kronos-mini/small/base | 4.1M / 24.7M / 102.3M (seen in README) | 16 MB / 99 MB / 409 MB | base: about 1.6 GB plus activations | Inference trivial; fine-tuning base is feasible on 16 GB but slow; mini/small recommended |
| Chronos-2 | 120M (28M small) [snippet] | ~480 MB | inference only recommended | Use frozen |

I found **no reliable 2026 benchmark** of small-transformer *training* speed on M3/M4 comparing PyTorch-MPS and MLX; sources were older, op-level or inference-only ([TDS MLX vs MPS vs CUDA](https://towardsdatascience.com/mlx-vs-mps-vs-cuda-a-benchmark-c5737ca6efc9), [arXiv 2510.18921](https://arxiv.org/html/2510.18921v1), both [snippet]). They show MLX sometimes faster than MPS on specific ops, and that some MPS ops (e.g., BCE on M1/M2) were slow. Action: Milestone 0 includes a 1-hour benchmark of the chosen GRU/PatchTST on the user's actual machine (steps/sec after warm-up, fixed batch and sequence length) on CPU vs MPS vs MLX, then decide. Practical default: PyTorch with `device="mps"` (ecosystem compatibility with Chronos/Kronos/Time-Series-Library code); MLX only if the benchmark justifies a rewrite.

### 10.3 Local experiment tracking and versioning

- **MLflow, local**: use the SQLite backend (`sqlite:///mlflow.db`). Since MLflow 3.7.0 SQLite is the default and the filesystem (`./mlruns`) backend is deprecated, with later versions requiring an opt-in env var (`MLFLOW_ALLOW_FILE_STORE`) ([MLflow backend-store docs](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store.html), [migration guide](https://mlflow.org/docs/latest/self-hosting/migrate-from-file-store/), [snippet]; the 3.13+ enforcement claim comes from a third-party PR and is unverified). Use `mlflow ui` on localhost. Log: label_spec hash, data hash, params, metrics, calibration plots, model artifact, and a **trial counter for DSR**.
- **MLflow Model Registry** (local) gives the champion/challenger aliases ("champion", "challenger", "shadow"). Verify registry works with the SQLite store in your installed version before relying on it.
- **DVC**: version parquet datasets and label sets in the repo with a local or external-drive remote (no cloud). Pipeline stages (`dvc.yaml`): `bars -> events -> labels -> features -> train -> evaluate`.
- **Optuna with SQLite storage** (`sqlite:///optuna.db`): tune LightGBM/encoder hyperparameters; every Optuna trial counts toward N in DSR. Use a time-aware objective (CPCV mean OOS log-loss or R_net, with std penalty).
- **No W&B cloud.** TensorBoard (local) is a fine alternative; FreqAI itself defaults `activate_tensorboard` to True [seen].
- Reproducibility: pin seeds, record library versions, store raw feature matrices hash. For NN, report mean±std over several seeds (Qlib does 20 seeds).

### 10.4 Local serving

- Champion model loaded in the trading process (FreqAI keeps the newest model in RAM and trains in a separate thread; do the same with a separate training process via `launchd`/cron so training never blocks inference).
- Model files: LightGBM text/`.txt`, PyTorch `state_dict` + preprocessing config + calibrator, all in one versioned folder like FreqAI's `sub-train-*` directories.
- Apple Silicon: keep sleep/thermal behavior in mind for long training jobs (open question for track 6, not tested here).

### 10.5 Where Claude (API) can sensibly help, off the critical path

| Use | Why safe | Constraint |
|---|---|---|
| Label news events (e.g., "earnings beat", "regulatory action", "hack") into a fixed taxonomy; output becomes categorical *features* for the meta-model | Offline, batched, cacheable | Point-in-time discipline: only text published before `t`; freeze outputs by (article id, model version, prompt hash). Re-running a newer Claude on old text changes history, so version it. Never let the model see outcomes |
| Extract structured features from text (sentiment, entity, event magnitude) | Same | Treat as noisy features; validate incremental lift via the same baselines (section 7). Local FinBERT is a zero-API alternative |
| Post-hoc trade explanations / daily review notes / anomaly summaries ("why did the champion lose this week?") | After the fact; no feedback to model or orders | Feed it logged features, SHAP values and context; flag that explanations are narratives, not causal proof |
| Help with experiment bookkeeping (write MLflow run summaries, generate research notes) | Dev-time only | |
| Do NOT: let Claude score trades live, set thresholds, or label training targets from future price information | Would leak into training/inference path and into the DSR trial count | |

If Claude-derived text features are used in the live model, they enter the live critical path in one place (the feature builder). Provide a fallback (feature = missing) so an API outage degrades gracefully rather than halting trading.

---

## 11. Community findings (with reach notes)

**Reachability**: Reddit (www.reddit.com, old.reddit JSON, redlib mirrors) was **not reachable** from this environment (fetch blocked / HTTP 403 / DNS failure), and `site:reddit.com` queries returned no Reddit results. So I have **no first-hand Reddit quotes** for r/algotrading, r/MachineLearning or r/quant. Search snippets surfaced titles of r/quant threads ("How you manage ML drift", Apr 2025: [redlib mirror](https://redlib.hackliberty.org/r/quant/comments/1jsw5m1/how_you_manage_ml_drift); "XGBoost in prediction": [mirror](https://redlib.hyperreal.coffee/r/quant/comments/1kgilnv/xgboost_in_prediction)) but I could not open them. Treat them as leads for the user to read manually. **X and Instagram were not reachable/searchable** with the tools available. YouTube: no transcripts retrievable; a search turned up creator pages only (e.g., Quantreo's Lucas claims to show live results; I could not retrieve figures). Hacker News was reachable (Algolia API).

What I could verify:

- **HN: RL trading paper thread** (2020-04-29, [item 23022864](https://news.ycombinator.com/item?id=23022864) [seen]): quant commenters say academic trading papers end in historic backtests; backtests omit front-running, latency, fees, slippage; a rhetorical but useful test is "what inefficiency does this exploit?" One commenter counters that a sequential, non-overlapping test split can't overfit the test set, which is true for that single split but ignores selection across many attempts.
- **HN: PyBroker** (2023, [item 35084227](https://news.ycombinator.com/item?id=35084227)): 70 points; I did not read the comments.
- **HN: AFML package** (2019, [item 20871769](https://news.ycombinator.com/item?id=20871769)): small thread; confirms MLFinLab's origin as a community AFML package before it went commercial [snippet].
- **QuantConnect forum** (above): meta-labeling lowered average Sharpe in one user's grid, and another user suspected their own leakage from not splitting training data ([thread](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/) [seen]).
- **MQL5 live reports**: the PPO and behavioural-cloning live logs above ([forum](https://www.mql5.com/en/forum/519231) [seen]); an MQL5 series on triple-barrier labeling with LightGBM and purged walk-forward evaluates by AUC and reminds that 0.50 is a coin flip ([article](https://www.mql5.com/en/articles/18864) [snippet]).
- **Leakage and live-gap pieces**: a commodities DRL paper says a ML model will readily exploit look-ahead in data and then fail to generalize ([arXiv 2308.01910](https://arxiv.org/pdf/2308.01910) [snippet]); QuantConnect docs list custom-dataset look-ahead as a source of live/backtest divergence ([docs](https://www.quantconnect.com/docs/v2/our-platform/live-trading/reconciliation) [snippet]); a practitioner checklist notes fundamentals joined on period end instead of release date trade on the future ([DEV](https://dev.to/tradevodata/how-to-detect-lookahead-bias-in-a-backtest-a-practical-checklist-2cb6) [snippet]); an article claims backtest Sharpe of 4 landing near 0.5 live is common ([techinterview.org](https://www.techinterview.org/post/3233477314/why-backtest-sharpe-collapses-live/?format=md) [snippet], secondary).
- **Kaggle/Numerai**: tabular, time-aware validation and ensembles of GBM and small NN dominate; leaderboard shakeups are the cost of overfitting to public data ([Jane Street blog](https://asterblogs.netlify.app/jane-street-ml), [Kaggle shake-up handbook](https://medium.com/global-maksimum-data-information-technologies/kaggle-handbook-tips-tricks-to-survive-a-kaggle-shake-up-23675beed05e), both [snippet]).
- **Practitioner anecdote for GBM+triple barrier** (single author, no methodology): triple-barrier labels were the biggest improvement; SHAP pruning 200 to 30 features gave +3% OOS accuracy ([DEV](https://dev.to/stefano_viana_dda882cfae5/how-i-built-a-profitable-freqai-plugin-using-institutional-ml-techniques-1l9k) [snippet]).

Honest summary: the verifiable community signal is "costs and leakage kill most results; simple models with strict time-aware validation survive; RL and deep nets are mostly unproven live". I could not collect large-sample live results for ML classifiers specifically.

---

## 12. Experiment roadmap with go/no-go gates

Each milestone logs all trials to MLflow; N feeds DSR. All results include 2x cost stress.

**M0: Harness and benchmark (about 1 week)**
- Build point-in-time data snapshot (DVC), event sampler, triple-barrier labeler (adopt or vendor mlfinpy/finmlkit; unit-test it against hand-computed cases, including barrier touch on the same bar and gap handling), purged/embargoed splitter, CPCV via skfolio or purged-cross-validation.
- Benchmark CPU vs MPS vs MLX for a small GRU on the user's Mac.
- Leakage tests: permuted labels give chance performance; features shifted by +1 bar degrade (they should not improve).
- Go: label-permutation test passes, and a known-null synthetic market (random walk with costs) yields no edge.

**M1: Baselines (1 to 2 weeks)**
- Always-take, logistic, DLinear-style, LightGBM/XGBoost/CatBoost on features. Calibration (isotonic) and p* threshold. CPCV with at least 3 paths. DSR with true N.
- Go: some baseline shows positive mean R_net after costs on CPCV paths with DSR above a pre-agreed bar (e.g., DSR probability above 0.95) and survives 2x cost stress. **No-go: if no baseline shows edge, stop; deep encoders will not rescue a missing signal, and the only productive moves are better features/data/market choice.**

**M2: Meta-labeling test (about 1 week)**
- Compare "take all primary signals" vs meta-model gating, with and without regime/text features.
- Go: meta-model improves mean R_net and Sharpe over take-all across CPCV paths (not just precision). No-go: drop gating, keep p̂/Ê for sizing only or drop the secondary model.

**M3: Encoder bake-off (2 to 3 weeks)**
- Small GRU/TCN with two heads; MiniRocket features; frozen Chronos-2/Kronos-mini/small embeddings into LightGBM; optional SSL pretraining on a larger unlabeled history.
- Report mean±std over at least 5 seeds.
- Go: beats best M1 baseline by more than seed noise on CPCV and on the held-out final period, with equal or better calibration. No-go: keep GBM as the model; park encoders.

**M4: Progressive training (2 weeks)**
- Walk-forward harness with window type/length/cadence as hyperparameters; compare static, sliding, expanding+recency weights, warm-start with replay; add ADWIN/Page-Hinkley on the error stream; implement model-age kill switch and OOD refuse-to-predict.
- Go: scheduled retrain beats static on out-of-sample blocks in a majority of folds. Warm-start/continual adopted only if it beats scratch refit.

**M5: Champion/challenger + shadow (4 or more weeks live-time)**
- MLflow registry aliases, nightly retrain job, shadow scoring against live prices with realistic fills.
- Go to paper trading (track 6) when: shadow scores' realized calibration matches backtest calibration within tolerance over at least K events (K chosen to give meaningful confidence intervals, perhaps 100 to 300), no leakage found, and model passes all monitors.
- Go to small live only after paper P&L is within the backtest confidence band including costs.

**M6 (optional): Text and cross-asset features**
- Claude-labeled event features and FinBERT embeddings; cross-asset context. Go only on incremental CPCV lift.

Kill criteria for the whole track: if M1 fails after reasonable feature work on two instruments, or if live shadow edge is zero within CI after M5, redirect effort to (a) different markets/horizons or (b) pure risk/execution value, not bigger models.

---

## 13. Open questions

1. Instrument universe and bar frequency (crypto vs equities vs FX; daily vs intraday). This changes label horizons, window lengths, cost model and whether cross-sectional ranking (option D) matters.
2. Where does the primary signal come from: rule-based, the LLM agents (track 1), or the forecaster (track 3)? Meta-labeling requires one; otherwise train a both-sides triple-barrier classifier.
3. Realistic cost/slippage model per venue: the biggest source of live-vs-backtest gap in the evidence.
4. Does the user want a single model across assets (pooled, with asset embeddings) or per-asset models? Pooling helps sample size; evidence not gathered here.
5. Data availability for point-in-time text/news (track 1 interplay): archive with publication timestamps needed from day one.
6. Independent replication of "CPCV beats walk-forward" on real data: I found only the synthetic-data study.
7. Whether Kronos or Chronos-2 embeddings help for this task: no independent evidence for trade-outcome classification; must be tested in M3.
8. Tools I did not verify: Joubert's meta-labeling paper full text, River's own docs, TimesNet paper details, Jesse's ML docs, TimesFM size, MLX vs MPS training speed on the user's chip.
9. Licensing: Freqtrade is GPL-3.0 and pypbo AGPL-3.0; decide whether the project will be distributed before borrowing code from them.
10. Apple Silicon assumption: confirm chip and RAM (16 GB vs 32 GB or more) before committing to the MPS/MLX path.
