"""TimesFM 2.5 (200M, Apache-2.0) worker. Input is LOG PRICE; output quantiles are cumulative log returns."""
import sys

import numpy as np
import timesfm

z = np.load(sys.argv[1])
ohlcv, H, Q = z["ohlcv"], [int(h) for h in z["horizons"]], [float(q) for q in z["quantiles"]]
n, L = len(ohlcv), ohlcv.shape[1]
model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch", torch_compile=False)
horizon = max(H)
model.compile(timesfm.ForecastConfig(max_context=L, max_horizon=horizon, normalize_inputs=True, use_continuous_quantile_head=True,
                                     force_flip_invariance=True, infer_is_positive=False, fix_quantile_crossing=True,
                                     per_core_batch_size=32))
# quantile_forecast is (n, horizon, 10): the mean first, then the 10th to 90th percentiles
levels = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
cube = np.zeros((n, len(H), len(Q)))
CHUNK = 128
for s in range(0, n, CHUNK):
    logp = [np.log(ohlcv[i, :, 3]) for i in range(s, min(s + CHUNK, n))]
    _point, quant = model.forecast(horizon=horizon, inputs=logp)
    quant = np.asarray(quant)
    for r, lp in enumerate(logp):
        for j, h in enumerate(H):
            for k, q in enumerate(Q):
                cube[s + r, j, k] = quant[r, h - 1, 1 + int(np.argmin(np.abs(np.array(levels) - q)))] - lp[-1]
np.savez(sys.argv[2], cube=cube)
