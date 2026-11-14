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
sys.path.insert(0, os.environ["KRONOS_SRC"])
from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402  (third-party code from the pinned checkout)

z = np.load(a.inp)
ohlcv, ts, H, Q = z["ohlcv"], z["ts"], [int(h) for h in z["horizons"]], [float(q) for q in z["quantiles"]]
device = "mps" if torch.backends.mps.is_available() else "cpu"
tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
mdl = Kronos.from_pretrained("NeoQuasar/Kronos-small")
pred = KronosPredictor(mdl, tok, device=device, max_context=512)
hmax = max(H)
cube = np.zeros((len(ohlcv), len(H), len(Q)))
for i in range(len(ohlcv)):
    x = pd.DataFrame(ohlcv[i], columns=["open", "high", "low", "close", "volume"])
    xt = pd.Series(pd.to_datetime(ts[i] * 86400, unit="s"))
    yt = pd.Series(pd.date_range(xt.iloc[-1] + pd.Timedelta(days=1), periods=hmax, freq="D"))
    last = float(ohlcv[i, -1, 3])
    paths = []
    for k in range(a.samples):
        torch.manual_seed(1000 + k)
        out = pred.predict(df=x, x_timestamp=xt, y_timestamp=yt, pred_len=hmax, T=1.0, top_p=0.9, sample_count=1)
        paths.append(np.log(out["close"].to_numpy(dtype=float) / last))
    paths = np.asarray(paths)                                  # (samples, hmax)
    for j, h in enumerate(H):
        cube[i, j] = np.quantile(paths[:, h - 1], Q)
np.savez(a.out, cube=cube)
