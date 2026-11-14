"""PI-Net v1 models (market and forecast channels) and out-of-sample path prediction.

Every model predicts two things for a candidate long trade, as an (n, 2) array:
  column 0  p  probability the trade ends with positive net R
  column 1  e  expected net R, the profitability index

Hyperparameters are fixed in advance and NOT tuned on the evaluation data. Any change to them is a new
trial and must be counted in the Deflated Sharpe.
"""

from __future__ import annotations

from typing import Callable, Protocol

import numpy as np

from .features import Dataset
from .nulltests import RidgeLogit
from .splits import CombinatorialPurgedCV

R_CLIP = (-1.5, 2.5)


class PIModel(Protocol):
    def fit(self, X: np.ndarray, y: np.ndarray, r: np.ndarray, aux: np.ndarray | None = None) -> "PIModel": ...
    def predict(self, X: np.ndarray) -> np.ndarray: ...


class RidgeLinear:
    def __init__(self, l2: float = 10.0):
        self.l2 = l2

    def fit(self, X, y):
        self.mu, self.sd = np.nanmean(X, 0), np.nanstd(X, 0) + 1e-12
        Z = np.column_stack([np.ones(len(X)), np.nan_to_num((X - self.mu) / self.sd)])
        reg = self.l2 * np.eye(Z.shape[1])
        reg[0, 0] = 0
        self.w = np.linalg.solve(Z.T @ Z + reg, Z.T @ y)
        return self

    def predict(self, X):
        return np.column_stack([np.ones(len(X)), np.nan_to_num((X - self.mu) / self.sd)]) @ self.w


class LinearPI:
    """Ridge logistic regression for p and ridge linear regression for e. The simple baseline model."""

    def fit(self, X, y, r, aux=None):
        X = np.nan_to_num(X.astype(float))
        self.clf = RidgeLogit(l2=10.0).fit(X, y)
        self.reg = RidgeLinear(l2=10.0).fit(X, np.clip(r, *R_CLIP))
        return self

    def predict(self, X):
        X = np.nan_to_num(X.astype(float))
        return np.column_stack([self.clf.predict_proba(X), self.reg.predict(X)])


class LgbmPI:
    """Two small gradient-boosted heads over the same features (the baseline the fusion net must beat)."""

    def __init__(self, rounds: int = 150, lr: float = 0.03, leaves: int = 6, min_leaf: int = 80, seed: int = 0):
        self.rounds, self.lr, self.leaves, self.min_leaf, self.seed = rounds, lr, leaves, min_leaf, seed

    def _params(self, objective: str) -> dict:
        return dict(objective=objective, learning_rate=self.lr, num_leaves=self.leaves, min_data_in_leaf=self.min_leaf,
                    feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1,
                    seed=self.seed, num_threads=4)

    def fit(self, X, y, r, aux=None):
        import lightgbm as lgb

        self.clf = lgb.train(self._params("binary"), lgb.Dataset(X, y), self.rounds)
        self.reg = lgb.train(self._params("regression"), lgb.Dataset(X, np.clip(r, *R_CLIP)), self.rounds)
        return self

    def predict(self, X):
        return np.column_stack([self.clf.predict(X), self.reg.predict(X)])


def cpcv_predictions(model_factory: Callable[[], PIModel], ds: Dataset, cv: CombinatorialPurgedCV,
                     X: np.ndarray | None = None, y=None, r=None) -> list[np.ndarray]:
    """One (n, 2) array of out-of-sample predictions per CPCV path. X, y, r default to the dataset's own;
    the null tests pass shifted outcomes here."""
    X = ds.X if X is None else X
    y = ds.y if y is None else y
    r = ds.r_net if r is None else r
    n = len(ds)
    fitted = []
    for train, test in cv.split(ds.t0, ds.t1):
        model = model_factory().fit(X[train], y[train], r[train], ds.aux[train])
        fitted.append((test, model.predict(X[test])))
    group = cv.group_of(n)
    paths = []
    for path in cv.paths():
        out = np.full((n, 2), np.nan)
        for split_idx, g in path:
            test, pred = fitted[split_idx]
            mask = group[test] == g
            out[test[mask]] = pred[mask]
        paths.append(out)
    return paths


def trade_score(pred: np.ndarray, r: np.ndarray, min_trades: int = 30) -> float:
    """Mean net R of the trades the model takes (e > 0) minus the mean of taking every candidate."""
    take = pred[:, 1] > 0
    return float(r[take].mean() - r.mean()) if take.sum() >= min_trades else 0.0
