"""Pure numpy helper shared by sampling-based workers (Kronos). Kept separate so the main project can test it without torch."""
import numpy as np


def summarize(samples, quantiles, min_valid_fraction=2 / 3):
    """samples: (n_paths, n_series, hmax) cumulative log returns, NaN where a path left the valid price range.
    Returns (cube (n_series, H?, Q) is built by the caller from per-horizon columns; here we return, for each series,
    the boolean mask of valid paths and whether the series has enough of them)."""
    n_paths, n_series, _ = samples.shape
    valid = np.isfinite(samples).all(axis=2)                     # (n_paths, n_series): a path is valid only if every day is finite
    ok = valid.sum(axis=0) >= int(np.ceil(min_valid_fraction * n_paths))
    return valid, ok


def quantile_cube(samples, horizons, quantiles, min_valid_fraction=2 / 3):
    """(n_series, len(horizons), len(quantiles)) quantiles over the valid paths; rows without enough valid paths are all NaN.
    Also returns the number of invalid paths per series."""
    valid, ok = summarize(samples, quantiles, min_valid_fraction)
    n_series = samples.shape[1]
    cube = np.full((n_series, len(horizons), len(quantiles)), np.nan)
    for r in range(n_series):
        if not ok[r]:
            continue
        good = samples[valid[:, r], r, :]
        for j, h in enumerate(horizons):
            cube[r, j] = np.quantile(good[:, h - 1], quantiles)
    return cube, (~valid).sum(axis=0)
