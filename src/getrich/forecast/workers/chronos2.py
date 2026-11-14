"""Chronos-2 worker. Runs in its own environment (see runner.py). Reads in.npz, writes out.npz with cube (n, H, Q).

The series fed to the model is LOG PRICE, so the forecast at step h minus the last log price is the cumulative log return."""
import sys

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

z = np.load(sys.argv[1])
ohlcv, ts, H, Q = z["ohlcv"], z["ts"], [int(h) for h in z["horizons"]], [float(q) for q in z["quantiles"]]
n = len(ohlcv)
device = "mps" if torch.backends.mps.is_available() else "cpu"
pipe = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=device)
cube = np.zeros((n, len(H), len(Q)))
CHUNK = 64
for s in range(0, n, CHUNK):
    frames, last = [], {}
    for i in range(s, min(s + CHUNK, n)):
        logp = np.log(ohlcv[i, :, 3])
        last[i] = logp[-1]
        frames.append(pd.DataFrame({"id": str(i), "timestamp": pd.to_datetime(ts[i] * 86400, unit="s"), "target": logp}))
    pred = pipe.predict_df(pd.concat(frames, ignore_index=True), prediction_length=max(H), quantile_levels=Q,
                           id_column="id", timestamp_column="timestamp", target="target")
    pred = pred.reset_index() if "id" not in pred.columns else pred
    qcols = {}
    for c in pred.columns:
        try:
            qcols[float(c)] = c
        except (TypeError, ValueError):
            pass
    for i in range(s, min(s + CHUNK, n)):
        g = pred[pred["id"].astype(str) == str(i)].sort_values("timestamp")
        for j, h in enumerate(H):
            for k, q in enumerate(Q):
                col = qcols[min(qcols, key=lambda x: abs(x - q))]
                cube[i, j, k] = float(g.iloc[h - 1][col]) - last[i]
np.savez(sys.argv[2], cube=cube)
