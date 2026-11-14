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

## Status

Built and tested (336 tests, none touching a model, network or exchange): the interface, causal generation and cache, features, evaluation, the isolation runner, the registry, fetch with lock verification, the three workers (valid Python written to the documented APIs, **not yet executed** because no weights are fetched), the CLI and the dataset channel.

Not done: any real forecast. That needs the downloads below. TTM and the volatility benchmark against HAR are also not done.

## To run (after the downloads are approved)

```bash
uv run getrich forecast-fetch chronos2          # 478 MB
uv run getrich forecast-run chronos2            # daily origins, BTC and ETH
uv run getrich forecast-eval --write            # docs/forecast-eval.md
```
Kronos needs `forecast-fetch-code`, a read of its Python files, and `reviewed: true` in the lock before it will run. It is slow (about a dozen sampled paths per forecast), so it defaults to every 5th day, and `--since 2025-08-02` limits it to the window that can be judged.
