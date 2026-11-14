"""Run ONE PI-Net model's CPCV evaluation in its own process.

Why a separate process: on macOS, PyTorch and LightGBM each bundle their own OpenMP runtime, and using both
in one process aborts it. The usual workaround (KMP_DUPLICATE_LIB_OK) is documented as possibly giving wrong
results, which is not acceptable here. So every model runs in a fresh process and the parent loads neither.

  python -m getrich.eval.pinet_worker --model lgbm --out preds.npz [--null 40]
  python -m getrich.eval.pinet_worker --model fusion --synthetic 0.4 --seed 3     (controls; prints JSON)

Output npz: preds (paths, n, 2), real_score, null_scores, p_value, and the row order used.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from . import nulltests, pinet
from .features import Dataset, make_dataset
from .splits import CombinatorialPurgedCV

HORIZON_DAYS = 10
EMBARGO = np.timedelta64(6, "D")
META_EMBARGO = np.timedelta64(11, "D")
META_KWARGS = dict(tp_mult=4.0, sl_mult=2.0, horizon=20, primary_min_votes=2 / 3)   # fixed in docs/preregistration-meta-label.md
SYNTH_IDX = {"market": [0, 1], "forecast": [2], "context": [3, 4]}


def _cv(embargo=EMBARGO) -> CombinatorialPurgedCV:
    return CombinatorialPurgedCV(6, 2, embargo=embargo)


def synthetic_dataset(alpha: float, seed: int, n: int = 1800) -> Dataset:
    import pandas as pd

    w = nulltests.make_world(n=n, alpha=alpha, seed=seed)
    return Dataset(X=w["X"].astype(np.float32), y=w["y"], r_net=w["r"], r_gross=w["r"], cost_r=np.zeros(n), t0=w["t0"], t1=w["t1"],
                   asset=np.array(["A"] * n), bar=pd.DatetimeIndex(w["t0"]), aux=np.full((n, 2), np.nan),
                   columns=["m0", "m1", "f0", "c0", "c1"],
                   channels={"market": ["m0", "m1"], "forecast": ["f0"], "context": ["c0", "c1"]})


def make_factory(name: str, ds: Dataset, epochs: int | None = None):
    if name == "linear":
        return pinet.LinearPI
    if name == "lgbm":
        return pinet.LgbmPI
    if name == "fusion":
        from .fusion import FusionPI

        idx = {k: ds.channel_idx(k) for k in ds.channels}
        kw = {"epochs": epochs} if epochs else {}
        return lambda: FusionPI(idx, **kw)
    raise ValueError(f"unknown model {name!r}")


def evaluate(name: str, ds: Dataset, n_null: int = 0, seed: int = 0, epochs: int | None = None, embargo=EMBARGO) -> dict:
    cv, factory = _cv(embargo), make_factory(name, ds, epochs)
    paths = pinet.cpcv_predictions(factory, ds, cv)
    real = float(np.mean([pinet.trade_score(p, ds.r_net) for p in paths]))
    out = {"preds": np.stack(paths), "real_score": real, "null_scores": np.array([]), "p_value": float("nan")}
    if n_null:
        rng = np.random.default_rng(seed)
        n = len(ds)
        null = np.empty(n_null)
        for i in range(n_null):
            s = int(rng.integers(40, n - 40))
            y_n, r_n = np.roll(ds.y, s), np.roll(ds.r_net, s)
            null[i] = np.mean([pinet.trade_score(p, r_n) for p in pinet.cpcv_predictions(factory, ds, cv, y=y_n, r=r_n)])
        out["null_scores"] = null
        out["p_value"] = (1 + float((null >= real).sum())) / (1 + n_null)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, choices=["linear", "lgbm", "fusion"])
    p.add_argument("--out")
    p.add_argument("--null", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--synthetic", type=float, help="alpha of a synthetic world (control mode, prints JSON)")
    p.add_argument("--epochs", type=int)
    p.add_argument("--meta", action="store_true", help="meta-label experiment: trend-entry days, 4/2 sigma, 20-day horizon")
    a = p.parse_args(argv)
    if a.synthetic is not None:
        ds = synthetic_dataset(a.synthetic, a.seed)
    elif a.meta:
        ds = make_dataset(**META_KWARGS)
    else:
        ds = make_dataset()
    res = evaluate(a.model, ds, a.null, a.seed, a.epochs, META_EMBARGO if a.meta else EMBARGO)
    if a.synthetic is not None:
        print(json.dumps({"model": a.model, "alpha": a.synthetic, "score": res["real_score"], "p": res["p_value"]}))
    if a.out:
        np.savez(a.out, preds=res["preds"], real_score=res["real_score"], null_scores=res["null_scores"], p_value=res["p_value"],
                 t0=ds.t0.astype("int64"), asset=ds.asset)
        print(f"wrote {a.out}: score {res['real_score']:+.4f} R, p = {res['p_value']:.3f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
