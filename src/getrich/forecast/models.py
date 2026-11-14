"""The foundation forecasters the architecture plans, and exactly what each one needs. Sizes and facts are from the official
Hugging Face model cards and file listings read on 2026-11-14 (docs/forecast-models.md)."""

from __future__ import annotations

import json
from pathlib import Path

from .. import config
from .runner import ModelSpec, SubprocessForecaster

SPECS: dict[str, ModelSpec] = {
    "kronos_small": ModelSpec(
        name="kronos_small", release="2025-08-02", context_len=512, worker="kronos.py", stride=5, batch=40, timeout_s=8 * 3600,
        requirements=["torch", "numpy", "pandas", "einops", "huggingface_hub", "safetensors", "tqdm"],
        repos=[{"repo": "NeoQuasar/Kronos-small", "allow": ["*.safetensors", "config.json"]},
               {"repo": "NeoQuasar/Kronos-Tokenizer-base", "allow": ["*.safetensors", "config.json"]}],
        extra_args=["--samples", "12"],
        note="Candle-native (OHLCV). Needs the Kronos source from GitHub (not on PyPI); reviewed and pinned by `forecast-fetch-code`."),
    "chronos2": ModelSpec(
        name="chronos2", release="2025-10-20", context_len=512, worker="chronos2.py", stride=1, batch=256,
        requirements=["chronos-forecasting>=2.0", "torch", "pandas", "numpy"],
        repos=[{"repo": "amazon/chronos-2", "allow": ["model.safetensors", "config.json"]}]),
    "timesfm25": ModelSpec(
        name="timesfm25", release="2025-09-15", context_len=512, worker="timesfm25.py", stride=1, batch=256,
        requirements=["timesfm[torch]", "torch", "numpy"],
        repos=[{"repo": "google/timesfm-2.5-200m-pytorch", "allow": ["model.safetensors", "config.json"]}],
        note="Apache-2.0 2.5 weights. 3.0 is deliberately NOT used: its weights are non-commercial."),
}


def kronos_src() -> Path:
    return config.root() / "models" / "kronos-src"


def get(name: str, **kw) -> SubprocessForecaster:
    if name not in SPECS:
        raise KeyError(f"unknown forecaster {name!r}; known: {sorted(SPECS)}")
    if name.startswith("kronos") and "env" not in kw:
        kw["env"] = {"KRONOS_SRC": str(kronos_src())}
    return SubprocessForecaster(SPECS[name], **kw)


def lock_path() -> Path:
    return config.root() / "config" / "forecast_models.lock.json"


def load_lock() -> dict:
    p = lock_path()
    return json.loads(p.read_text()) if p.exists() else {}
