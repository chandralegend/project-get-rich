# Spike: can the forecasters and the PI-Net run inside Docker? (2026-11-16)

**Result: yes.** Linux arm64, CPU only, no network, in one image (`docker/models.Dockerfile`, 3.1 GB).

| Check | Result |
|---|---|
| Install on arm64 Linux in one environment (torch 2.15 CPU, chronos-forecasting 2.3.2, timesfm 3.0.2, LightGBM 4.7, numpy 2.5, pandas 3.1) | Works. No version conflicts, so one environment is enough (no per-worker environments). |
| Chronos-2, offline, 4 origins | 8 s. Output identical to the host's cached forecasts for the 3 origins the host had (max difference 0.0000). |
| TimesFM 2.5, offline, 4 origins | 6 s. Identical to the host cache (max difference 0.0000). |
| Kronos-small, 12 samples per origin, 4 origins | 92 s. Not identical, as expected: 12 sampled paths drawn on CPU instead of the Mac's GPU (median differs by up to 0.05, intervals by a similar amount). Kronos has no skill against a random walk either way. |
| New origin 2026-11-15 (not yet in the cache) | Computed by all three models, all finite. |
| Saved PI-Net (`pinet-lgbm-chronos2-nonews.pkl`, 35 features, trained on rows 2021-05-26 to 2026-10-25) | Loads and predicts in the container (needs `libgomp1` and the `getrich` source on the path). |
| Runtime isolation | `--network none`, no env file, weights and code mounted read-only. |

## What went wrong on the way (and the rules that follow)

1. **The first build was 18.8 GB.** The default PyPI torch wheel on arm64 carries the CUDA libraries. Install torch from `https://download.pytorch.org/whl/cpu`: the image is 3.1 GB.
2. **Docker Desktop's VM disk went read-only** (`ext4 ... emergency_ro`, 157 GB free, so not a full disk) a few minutes after the 18.8 GB image was exported. The live data volume became read-only for the api and scheduler, and so did other projects' containers. A Docker Desktop restart cleared it; the ledger verified intact (729 insights, chain intact). Cause not proven; the heavy image export is the likely trigger. Keep images small and avoid several-GB layer exports.
3. **Three of the four weight files copied during that event were silently damaged** (right size, wrong hash). Every copy of the weights must be verified against `config/forecast_models.lock.json` (`sha256sum -c`); this was done and all eight files match.

## Weights for the container

The host's Hugging Face cache points into a shared blob store, so mounting the model folders does not work. The four models are copied, with files resolved, into the named volume `getrich-models-hf` (1.4 GB) in the standard `hub/models--<org>--<name>/snapshots/<rev>/` layout, and mounted read-only at `/hf` with `HF_HOME=/hf`, `HF_HUB_OFFLINE=1`.

## Next (needs your go-ahead): see the plan in the conversation, phases 1 to 3.
