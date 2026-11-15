"""Kronos worker (candle-native, MIT). The Kronos source tree is a separate, reviewed and pinned checkout (see `forecast-fetch-code`);
its path is read from KRONOS_SRC. Kronos samples one candle path per call, so a distribution comes from repeating the call with
different seeds and taking empirical quantiles of the cumulative log return of the sampled closes."""
import argparse
import os
import sys

import numpy as np
import pandas as pd
import torch

ap = argparse.ArgumentParser()
ap.add_argument("inp")
ap.add_argument("out")
ap.add_argument("--samples", type=int, default=12)
a = ap.parse_args()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import quantile_cube  # noqa: E402  (our own pure numpy helper)
sys.path.insert(0, os.environ["KRONOS_SRC"])
from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402  (third-party code from the pinned checkout)

z = np.load(a.inp)
ohlcv, ts, H, Q = z["ohlcv"], z["ts"], [int(h) for h in z["horizons"]], [float(q) for q in z["quantiles"]]
device = "mps" if torch.backends.mps.is_available() and not os.environ.get("GETRICH_FORCE_CPU") else "cpu"
tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
mdl = Kronos.from_pretrained("NeoQuasar/Kronos-small")
pred = KronosPredictor(mdl, tok, device=device, max_context=512)
hmax = max(H)
n = len(ohlcv)
cube = np.zeros((n, len(H), len(Q)))
invalid = np.zeros(n, dtype=int)
CHUNK = 16                                                        # series per predict_batch call; all contexts have the same length
for s in range(0, n, CHUNK):
    idx = list(range(s, min(s + CHUNK, n)))
    dfs = [pd.DataFrame(ohlcv[i], columns=["open", "high", "low", "close", "volume"]) for i in idx]      # the predictor derives `amount` from volume
    xts = [pd.Series(pd.to_datetime(ts[i].astype("int64") * 86400, unit="s")) for i in idx]
    yts = [pd.Series(pd.date_range(x.iloc[-1] + pd.Timedelta(days=1), periods=hmax, freq="D")) for x in xts]
    last = np.array([ohlcv[i, -1, 3] for i in idx])
    samples = []
    for k in range(a.samples):
        torch.manual_seed(1000 + k)
        outs = pred.predict_batch(dfs, xts, yts, pred_len=hmax, T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False)
        samples.append([np.log(np.where(o["close"].to_numpy(dtype=float) > 0, o["close"].to_numpy(dtype=float), np.nan) / l) for o, l in zip(outs, last)])
    samples = np.asarray(samples)                                 # (samples, series, hmax)
    if os.environ.get("KRONOS_DUMP"):                             # debugging aid: keep every sampled path of this chunk
        np.save(os.environ["KRONOS_DUMP"] + f".{s}.npy", samples)
    c, bad = quantile_cube(samples, H, Q)                          # invalid paths are dropped and counted; too few valid ones leave a NaN row
    cube[idx] = c
    invalid[idx] = bad
    print(f"kronos: {min(s + CHUNK, n)}/{n}", file=sys.stderr, flush=True)
np.savez(a.out, cube=cube, invalid_paths=invalid)
