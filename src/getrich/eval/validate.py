"""`getrich validate-harness`: proves the harness can tell skill from luck before anything is judged by it.

Four controls on synthetic worlds where the truth is known:
  1. planted signal      a real (weak) signal exists            -> the harness must find it
  2. pure noise          no signal, overlapping labels           -> it must NOT find one (false-positive rate)
  3. shuffled labels     the planted world with outcomes shuffled -> the signal must vanish
  4. leaky model         noise world, a model that peeks at neighbouring samples in time:
                         naive shuffled K-fold shows 'skill', purged CPCV must not
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .nulltests import (NearestTimeModel, RidgeLogit, cpcv_scores, make_world, naive_kfold_scores, null_pvalue)
from .splits import CombinatorialPurgedCV

DAY = np.timedelta64(1, "D")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _cv(horizon: int) -> CombinatorialPurgedCV:
    return CombinatorialPurgedCV(6, 2, embargo=(horizon // 2 + 1) * DAY)


def run(n: int = 2000, n_null: int = 60, noise_seeds: int = 8) -> list[Check]:
    out: list[Check] = []

    w = make_world(n=n, alpha=0.30, seed=11)
    cv = _cv(w["horizon"])
    p_shift, real, _ = null_pvalue(RidgeLogit, w["X"], w["y"], w["r"], w["t0"], w["t1"], cv, kind="shift", n_null=n_null, seed=1)
    out.append(Check("planted signal is found", p_shift < 0.05 and real > 0.1,
                     f"score {real:+.3f} R, shift-null p = {p_shift:.3f} (need p < 0.05 and score > 0.1)"))

    rejections, pvals = 0, []
    for s in range(noise_seeds):
        wn = make_world(n=n, alpha=0.0, seed=100 + s)
        p, _, _ = null_pvalue(RidgeLogit, wn["X"], wn["y"], wn["r"], wn["t0"], wn["t1"], _cv(wn["horizon"]),
                              kind="shift", n_null=n_null, seed=s)
        pvals.append(p)
        rejections += p < 0.05
    allowed = max(2, int(0.05 * noise_seeds) + 2)
    out.append(Check("pure noise is not mistaken for skill", rejections <= allowed,
                     f"{rejections} of {noise_seeds} noise worlds rejected at 5% (allowed {allowed}); p-values {np.round(pvals, 2).tolist()}"))

    rng = np.random.default_rng(5)
    perm = rng.permutation(n)
    p_shuf, real_shuf, _ = null_pvalue(RidgeLogit, w["X"], w["y"][perm], w["r"][perm], w["t0"], w["t1"], cv,
                                       kind="shift", n_null=n_null, seed=2)
    out.append(Check("shuffled labels destroy the signal", real_shuf < 0.5 * real and p_shuf > 0.05,
                     f"score {real_shuf:+.3f} R vs {real:+.3f} unshuffled, shift-null p = {p_shuf:.3f} (need p > 0.05)"))

    leaky_naive, leaky_purged = [], []
    for s in range(5):
        wl = make_world(n=n, alpha=0.0, seed=200 + s)
        leaky_naive.append(naive_kfold_scores(NearestTimeModel, wl["time"], wl["y"], wl["r"], seed=s))
        leaky_purged.append(float(cpcv_scores(NearestTimeModel, wl["time"], wl["y"], wl["r"], wl["t0"], wl["t1"],
                                              _cv(wl["horizon"])).mean()))
    out.append(Check("naive K-fold is fooled by a leaky model, purged CPCV is not",
                     np.mean(leaky_naive) > 0.15 and abs(np.mean(leaky_purged)) < 0.15,
                     f"naive K-fold invents {np.mean(leaky_naive):+.3f} R of skill, purged CPCV finds {np.mean(leaky_purged):+.3f} R "
                     "(need naive > +0.15 and purged within +-0.15)"))
    return out
