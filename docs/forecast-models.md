# Foundation forecasters: what is planned, what is built, how they are judged

Date: 2026-11-14. The architecture (section 4.3) plans a forecast channel of HAR volatility plus pretrained forecasters. Phase 2 built only the HAR part and deferred the pretrained models, which was a gap against the plan. This closes the plumbing; the models themselves are evaluated before they are trusted.

## The models (from the official Hugging Face cards and file listings, read 2026-11-14)

| Model | Repo | Download | Licence | Released | What it gives |
|---|---|---:|---|---|---|
| Kronos-small (24.7M) + tokenizer | `NeoQuasar/Kronos-small`, `NeoQuasar/Kronos-Tokenizer-base` | 99 MB + 15.8 MB | MIT | 2025-08-02 (paper) | Sampled OHLCV candle paths; quantiles come from repeated sampling. Context 512. Source code is not on PyPI: it comes from `github.com/shiyu-coder/Kronos`. |
| Chronos-2 (120M) | `amazon/chronos-2` | 478 MB | Apache-2.0 | 2025-10-20 | Quantile forecasts at any levels. Context up to 8192. |
| TimesFM 2.5 (200M) | `google/timesfm-2.5-200m-pytorch` | 925 MB | Apache-2.0 | 2025-09-15 | Deciles plus a mean. |
| TinyTimeMixer r2 | `ibm-granite/granite-timeseries-ttm-r2` | 3.8 MB | Apache-2.0 | 2024 | Point forecasts only, no quantiles. For the volatility track, not built yet: the package pins torch below 2.12 and we run 2.15. |

Deliberately not used: TimesFM 3.0 (weights are non-commercial), Kronos-large (not public), Chronos-Bolt (superseded by Chronos-2). All weights are `safetensors`; none of the repos ship pickle or `trust_remote_code`. No card states a pretraining cutoff date, so the release date is the earliest origin that is certainly free of contamination.

## What the research said (research/03), and why they are still worth testing

Independent checks found Kronos with no skill against a random walk (BTC 24-hour skill -118%, direction 50/100, 10-90% coverage 21%), Kronos last on volatility against HAR-RV, and forecast intervals from time-series foundation models that are badly miscalibrated. The plan always called them "optional feature generators behind strict tests". The point of building them in is to run those tests on our data and have a real answer instead of a deferred one, not to assume they help.

## How they are used

- **Each model runs in its own process and environment** (`forecast/runner.py`, `uv run --no-project --with <requirements>`): dependency pins cannot touch our torch and LightGBM, the worker gets no API keys or project environment, and it runs with `HF_HUB_OFFLINE=1`, so it can only use weights that `forecast-fetch` downloaded on purpose.
- **`forecast-fetch` is the only download path.** It fetches exactly the files named in the registry, and records the revision, size and SHA-256 in `config/forecast_models.lock.json`; every run verifies the lock first. `forecast-fetch-code` clones Kronos's source for review and never runs it; `forecast-run` refuses until the source is marked `reviewed` in the lock.
- **Forecasts are walk-forward and cached**: the window handed to a model ends at the origin day (a test rewrites the future and shows the forecast does not move). Output is quantiles of the cumulative log return at 1, 5 and 20 days (levels 0.1, 0.3, 0.5, 0.7, 0.9, the ones every model can produce), computed from log price, so the series is scale-free.
- **Judged before use** (`getrich forecast-eval`, `docs/forecast-eval.md`): pinball-loss skill against a zero-drift random walk at the same volatility, a location-only skill, rank IC with a block-bootstrap interval, hit rate against the up rate, 80% and 40% coverage, and a Diebold-Mariano test with Newey-West errors. Windows: all history (contamination can only inflate it) and post-release only. The harness is tested to credit an oracle, give nothing to a random walk or to momentum on noise, give momentum credit when the data really trend, and expose an overconfident model through coverage.
- **Into the PI-Net only if they earn it.** `make_dataset(foundation_models=[...])` adds an optional `foundation` channel (per model: median, probability-up, width and skew, all scaled by volatility) and keeps only the rows that have it; the fusion network masks a channel whose inputs are missing. Training on the contaminated period would teach a model to over-trust the forecasts, so a PI-Net experiment with these features must use post-release rows only, which is about 13 months, roughly 800 pooled rows: enough for a linear blend and an ablation, not for the full fusion network.

## Status (superseded by the results section below)

Built and tested (336 tests, none touching a model, network or exchange): the interface, causal generation and cache, features, evaluation, the isolation runner, the registry, fetch with lock verification, the three workers (valid Python written to the documented APIs, **not yet executed** because no weights are fetched), the CLI and the dataset channel.

Not done: any real forecast. That needs the downloads below. TTM and the volatility benchmark against HAR are also not done.

## To run (after the downloads are approved)

```bash
uv run getrich forecast-fetch chronos2          # 478 MB
uv run getrich forecast-run chronos2            # daily origins, BTC and ETH
uv run getrich forecast-eval --write            # docs/forecast-eval.md
```
Kronos needs `forecast-fetch-code`, a read of its Python files, and `reviewed: true` in the lock before it will run. It is slow (about a dozen sampled paths per forecast), so it defaults to every 5th day, and `--since 2025-08-02` limits it to the window that can be judged.

## Record of what was fetched and reviewed (2026-11-14)

- Weights downloaded with `forecast-fetch`, each file hashed in a local lock (`config/forecast_models.lock.json`, gitignored because it holds cache paths): Kronos-small (99.0 MB) and its tokenizer (15.8 MB), Chronos-2 (477.9 MB), TimesFM 2.5 (925.2 MB).
- Kronos source: `https://github.com/shiyu-coder/Kronos` at commit `67b630e67f6a18c9e9be918d9b4337c960db1e9a`. The only files that are ever imported are `model/__init__.py`, `model/kronos.py` and `model/module.py` (1,252 lines). All three were read in full: they import only math, einops, torch, numpy, pandas, tqdm and huggingface_hub, and make no network calls, no subprocess, `eval`, `exec`, pickle, `torch.load` or file access. Their SHA-256 hashes are recorded in the lock and checked before every run, so a changed file blocks the run until it is read again.
  - `model/__init__.py` `f8f856ca3fedadca`
  - `model/kronos.py` `0a5f90282e2039c2`
  - `model/module.py` `a07edbadc0e96804`
- The Chronos-2 and TimesFM 2.5 workers were checked against the installed libraries' signatures (`chronos-forecasting` 2.3.2 and `timesfm` 3.0.2, which does include the 2.5 class) but have not run yet.
- Kronos-small ran on the post-release window (2025-08-02 onward) at about 4.4 seconds per forecast. First results, BTC: worse than a random walk at 1, 5 and 20 days (skill -0.28, -0.51, -0.52), no direction information, 80% bands that held 63%, 54% and 47% of the time. Full numbers: `getrich forecast-eval`.
- A bug found on the way: the cache used to be written once per symbol, so an interrupted run lost its batches. It is now written after every batch (tested).

## Results (2026-11-15)

All three models ran walk-forward on BTCUSDT and ETHUSDT (full report: [forecast-eval.md](forecast-eval.md); regenerate with `uv run getrich forecast-eval --write`). **None shows skill against a random walk, so none may influence a trade.**

| Model | Origins scored | Skill at 1, 5, 20 days | Direction (rank correlation, 20 days) | 80% band held, 1, 5, 20 days |
|---|---:|---|---|---|
| Chronos-2, all history | about 4,000 | -0.044, -0.009, -0.016 | -0.064 (-0.15, +0.02) | 82%, 78%, 76% |
| Chronos-2, after release | about 780 | -0.034, -0.019, -0.020 | -0.222 (-0.45, +0.00) | 83%, 81%, 74% |
| TimesFM 2.5, all history | about 4,000 | -0.047, -0.018, -0.040 | -0.100 (-0.19, -0.00) | 89%, 83%, 80% |
| TimesFM 2.5, after release | about 850 | -0.037, -0.022, -0.013 | +0.067 (-0.16, +0.28) | 89%, 85%, 81% |
| Kronos-small, after release | about 930 | -0.325, -0.619, -0.746 | +0.077 (-0.13, +0.27) | 63%, 57%, 45% |

Reading: Chronos-2 and TimesFM are about a random walk with fair bands; Kronos is clearly worse and overconfident. The full history may overlap what the models were trained on, which can only flatter them. TimesFM's direction is slightly anti-predictive over the full history; flipping it would be fitting the past and needs its own pre-registered test. Neighbouring days overlap, so the effective sample is roughly n divided by the horizon.

Bugs found by running them for real, both fixed with tests: Kronos sometimes samples paths whose price goes to zero (invalid paths are dropped and counted, an origin with fewer than 8 of 12 valid paths is recorded as failed and never retried), and TimesFM pads its input list in place to a multiple of its batch size, which broke the output indexing for a final chunk that was not a multiple of 32.

Still untested: Chronos-2 and TimesFM as volatility forecasters against HAR, and TinyTimeMixer (not built).
