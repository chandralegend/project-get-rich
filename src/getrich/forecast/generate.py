"""Walk-forward forecast generation. The window handed to a forecaster ends at the origin day: nothing later is visible to it."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..obs.events import emit
from .base import Cache, Forecaster, load_cache, save_cache, validate_cube

SERVICE = "forecast"
COLS = ["open", "high", "low", "close", "volume"]


def index_ns(index: pd.DatetimeIndex) -> np.ndarray:
    """UTC nanoseconds as int64, whatever resolution pandas stored the index in."""
    idx = index.tz_convert("UTC").tz_localize(None) if index.tz is not None else index
    return idx.to_numpy(dtype="datetime64[ns]").astype("int64")


def windows(bars: pd.DataFrame, origins_idx: np.ndarray, L: int) -> tuple[np.ndarray, np.ndarray]:
    ohlcv = bars[COLS].to_numpy(dtype=float)
    days = index_ns(bars.index) // 86_400_000_000_000
    X = np.stack([ohlcv[i - L + 1: i + 1] for i in origins_idx])          # ends AT the origin, never beyond
    T = np.stack([days[i - L + 1: i + 1] for i in origins_idx])
    return X, T


def origin_indices(bars: pd.DataFrame, L: int, stride: int, since: pd.Timestamp | None) -> np.ndarray:
    idx = np.arange(L - 1, len(bars), stride)
    if since is not None:
        idx = idx[bars.index[idx] >= since]
    return idx


def generate(fc: Forecaster, symbol: str, bars: pd.DataFrame, *, stride: int | None = None, since: pd.Timestamp | None = None,
             batch: int | None = None, max_new: int | None = None, progress=None) -> Cache:
    """Compute forecasts for origins not yet cached and add them to the cache. Origins are bar-open times of CLOSED daily bars."""
    stride = stride or fc.default_stride
    batch = batch or getattr(fc, "batch", 32)
    old = load_cache(fc.name, symbol)
    want = origin_indices(bars, fc.context_len, stride, since)
    ns = index_ns(bars.index)
    todo = want[~np.isin(ns[want], old.origins.astype("datetime64[ns]").astype("int64"))] if old and len(old) else want
    if max_new is not None:
        todo = todo[:max_new]
    merged, crossed = old, 0
    for s in range(0, len(todo), batch):
        part = todo[s: s + batch]
        X, T = windows(bars, part, fc.context_len)
        cube, n_cross = validate_cube(fc.forecast(X, T), len(part))
        crossed += n_cross
        new_o = ns[part].astype("datetime64[ns]")
        merged = Cache(fc.name, symbol, np.concatenate([merged.origins, new_o]) if merged and len(merged) else new_o,
                       np.concatenate([merged.cube, cube]) if merged and len(merged) else cube)
        save_cache(merged)                       # after EVERY batch: an interrupted run keeps everything finished so far
        if progress:
            progress(s + len(part), len(todo))
    if len(todo):
        emit("forecast.generated", service=SERVICE, model=fc.name, symbol=symbol, new=int(len(todo)), total=len(merged), crossing_fixed=crossed)
        return merged
    return old or Cache(fc.name, symbol, np.array([], dtype="datetime64[ns]"), np.zeros((0, 0, 0), dtype=np.float32))
