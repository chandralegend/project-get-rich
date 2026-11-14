"""Model scoring through CPCV, plus null tests that tell skill from luck.

Score of a model on one out-of-sample path: the mean net R of the trades it chose to take, minus the
mean net R of taking every candidate. Zero means no skill; it can be negative.

Two nulls:
  shuffle  permute outcomes across samples. Simple, but it destroys the outcomes' own serial structure
           (overlapping label windows make neighbouring outcomes alike), so it understates how lucky a
           score can get on real data.
  shift    circularly roll the outcomes against the features by a random offset. This keeps the outcomes'
           serial structure and breaks only their link to the features, so it is the statistically fairer
           null for overlapping labels. Use this one for p-values.
"""

from __future__ import annotations

from typing import Callable, Protocol

import numpy as np
import pandas as pd

from .splits import CombinatorialPurgedCV, PurgedKFold

MIN_TRADES = 30


class Model(Protocol):
    def fit(self, X: np.ndarray, y: np.ndarray) -> "Model": ...
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...


class RidgeLogit:
    """Small L2-regularised logistic regression (Newton steps). Enough for the harness controls."""

    def __init__(self, l2: float = 1.0, iters: int = 25):
        self.l2, self.iters = l2, iters

    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-12
        Z = np.column_stack([np.ones(len(X)), (X - self.mu) / self.sd])
        w = np.zeros(Z.shape[1])
        reg = self.l2 * np.eye(Z.shape[1])
        reg[0, 0] = 0.0
        for _ in range(self.iters):
            p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
            grad = Z.T @ (p - y) + reg @ w
            hess = (Z * (p * (1 - p))[:, None]).T @ Z + reg + 1e-9 * np.eye(Z.shape[1])
            step = np.linalg.solve(hess, grad)
            w -= step
            if np.max(np.abs(step)) < 1e-8:
                break
        self.w = w
        return self

    def predict_proba(self, X):
        Z = np.column_stack([np.ones(len(X)), (X - self.mu) / self.sd])
        return 1 / (1 + np.exp(-np.clip(Z @ self.w, -30, 30)))


class NearestTimeModel:
    """Deliberately leaky control: predicts a sample's label from the training sample closest in time.
    On overlapping labels this 'works' if neighbours are not purged, and cannot work if they are."""

    def fit(self, X, y):
        order = np.argsort(X[:, 0])
        self.t, self.y = X[order, 0], y[order].astype(float)
        return self

    def predict_proba(self, X):
        pos = np.clip(np.searchsorted(self.t, X[:, 0]), 1, len(self.t) - 1)
        left, right = self.t[pos - 1], self.t[pos]
        return np.where(np.abs(X[:, 0] - left) <= np.abs(right - X[:, 0]), self.y[pos - 1], self.y[pos])


def _score(p: np.ndarray, r: np.ndarray, thr: float) -> float:
    take = p > thr
    return float(r[take].mean() - r.mean()) if take.sum() >= MIN_TRADES else 0.0


def cpcv_scores(model_factory: Callable[[], Model], X, y, r, t0, t1, cv: CombinatorialPurgedCV, thr: float = 0.5) -> np.ndarray:
    """One score per out-of-sample path."""
    n = len(y)
    fitted = []
    for train, test in cv.split(t0, t1):
        m = model_factory().fit(X[train], y[train])
        fitted.append((test, m.predict_proba(X[test])))
    group = cv.group_of(n)
    scores = []
    for path in cv.paths():
        p = np.full(n, np.nan)
        for split_idx, g in path:
            test, proba = fitted[split_idx]
            mask = group[test] == g
            p[test[mask]] = proba[mask]
        scores.append(_score(p, r, thr))
    return np.asarray(scores)


def naive_kfold_scores(model_factory, X, y, r, n_splits: int = 5, thr: float = 0.5, seed: int = 0) -> float:
    """What people do wrong: shuffled K-fold with no purge or embargo. Used only as a control."""
    rng = np.random.default_rng(seed)
    n = len(y)
    folds = np.array_split(rng.permutation(n), n_splits)
    p = np.full(n, np.nan)
    for test in folds:
        train = np.setdiff1d(np.arange(n), test)
        p[test] = model_factory().fit(X[train], y[train]).predict_proba(X[test])
    return _score(p, r, thr)


def null_pvalue(
    model_factory, X, y, r, t0, t1, cv: CombinatorialPurgedCV, *, kind: str = "shift", n_null: int = 100,
    thr: float = 0.5, seed: int = 0, min_shift: int = 40,
) -> tuple[float, float, np.ndarray]:
    """Returns (p_value, real_score, null_scores). Real score = mean of the CPCV path scores."""
    rng = np.random.default_rng(seed)
    real = float(cpcv_scores(model_factory, X, y, r, t0, t1, cv, thr).mean())
    n = len(y)
    null = np.empty(n_null)
    for i in range(n_null):
        if kind == "shuffle":
            perm = rng.permutation(n)
            y_n, r_n = y[perm], r[perm]
        elif kind == "shift":
            s = int(rng.integers(min_shift, n - min_shift))
            y_n, r_n = np.roll(y, s), np.roll(r, s)
        else:
            raise ValueError("kind must be 'shuffle' or 'shift'")
        null[i] = cpcv_scores(model_factory, X, y_n, r_n, t0, t1, cv, thr).mean()
    return (1 + float((null >= real).sum())) / (1 + n_null), real, null


def make_world(n: int = 2000, alpha: float = 0.0, seed: int = 0, horizon: int = 10, n_noise: int = 4) -> dict:
    """A synthetic market of trade outcomes. Outcome r_i = alpha * f_i + the sum of `horizon` consecutive
    shocks, so outcomes of neighbouring samples overlap exactly as real triple-barrier labels do.
    alpha = 0 is a pure-noise world."""
    rng = np.random.default_rng(seed)
    eps = rng.normal(size=n + horizon)
    overlap = np.array([eps[i : i + horizon].sum() for i in range(n)]) / np.sqrt(horizon)
    f = rng.normal(size=n)
    r = alpha * f + overlap
    X = np.column_stack([f, rng.normal(size=(n, n_noise))])
    t0 = (np.datetime64("2018-01-01") + np.arange(n)).astype("datetime64[ns]")
    t1 = t0 + np.timedelta64(horizon, "D")
    return {"X": X, "y": (r > 0).astype(int), "r": r, "t0": t0, "t1": t1, "time": np.arange(n, dtype=float)[:, None], "horizon": horizon}
