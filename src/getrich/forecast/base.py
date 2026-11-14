"""The forecaster interface, and the walk-forward cache."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config

HORIZONS = (1, 5, 20)                       # days ahead
QUANTILES = (0.1, 0.3, 0.5, 0.7, 0.9)       # levels every supported model can produce (TimesFM gives deciles)


class Forecaster:
    """forecast(ohlcv, ts) -> cube of shape (n, len(HORIZONS), len(QUANTILES)): quantiles of the cumulative LOG RETURN from the last
    close in each window to h days later. ohlcv is (n, L, 5): open, high, low, close, volume. ts is (n, L): day number since 1970."""
    name = "?"
    release = pd.Timestamp("2100-01-01", tz="UTC")     # public release date: origins after it cannot be contaminated by pretraining
    context_len = 256
    default_stride = 1

    def forecast(self, ohlcv: np.ndarray, ts: np.ndarray) -> np.ndarray:
        raise NotImplementedError


@dataclass
class Cache:
    model: str
    symbol: str
    origins: np.ndarray                     # datetime64[ns], the bar-open time of each origin day
    cube: np.ndarray                        # (n, H, Q) float32

    def __len__(self) -> int:
        return len(self.origins)


def cache_path(model: str, symbol: str) -> Path:
    return config.data_dir() / "forecasts" / model / f"{symbol}.npz"


def load_cache(model: str, symbol: str) -> Cache | None:
    p = cache_path(model, symbol)
    if not p.exists():
        return None
    z = np.load(p, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    if tuple(meta["horizons"]) != HORIZONS or tuple(meta["quantiles"]) != QUANTILES:
        raise RuntimeError(f"{p} was written with different horizons or quantiles than the code now uses; regenerate it")
    return Cache(model, symbol, z["origins"], z["cube"])


def save_cache(c: Cache) -> None:
    p = cache_path(c.model, c.symbol)
    p.parent.mkdir(parents=True, exist_ok=True)
    order = np.argsort(c.origins)
    np.savez_compressed(p, origins=c.origins[order], cube=c.cube[order].astype(np.float32),
                        meta=json.dumps({"horizons": list(HORIZONS), "quantiles": list(QUANTILES), "model": c.model}))


def validate_cube(cube: np.ndarray, n: int) -> tuple[np.ndarray, int]:
    """Shape and finiteness are hard requirements. Crossing quantiles are repaired by sorting and counted."""
    if cube.shape != (n, len(HORIZONS), len(QUANTILES)):
        raise ValueError(f"forecaster returned shape {cube.shape}, expected {(n, len(HORIZONS), len(QUANTILES))}")
    if not np.isfinite(cube).all():
        raise ValueError("forecaster returned non-finite values")
    fixed = np.sort(cube, axis=-1)
    return fixed, int((fixed != cube).any(axis=-1).sum())
