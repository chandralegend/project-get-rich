"""Judge a forecaster against a random walk before it is allowed anywhere near a trading model.

All scores are on cumulative log returns normalised by the volatility known at the origin (20-day EWMA daily sigma times sqrt(h)),
so BTC and ETH and calm and wild periods are comparable. The benchmark is a zero-drift Gaussian with that same scale: the
standard "no-change" forecast. Beating it needs real information about the location or the shape, not just a decent volatility.

Per horizon and window it reports:
  skill        1 - (model pinball loss / benchmark pinball loss). Positive means better than the random walk.
  location     the same, but using only the model's MEDIAN with the benchmark's scale: does the direction information help?
  IC           Spearman correlation between the model's normalised median and the realised normalised return, with a block-bootstrap interval
  hit          how often the sign of the median matched the sign of the outcome, next to how often the market simply went up
  coverage     how often the outcome fell inside the model's 10-90% and 30-70% bands (nominal 80% and 40%)
  DM           a Diebold-Mariano test of the loss difference with Newey-West errors, because overlapping horizons make errors correlated

Windows: "all" is every cached origin; "post_release" keeps origins on or after the model's public release date, which a model
cannot have seen in pretraining. Contamination could only inflate "all", so a model with no skill there has none after either.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

from ..eval.labels import daily_vol
from .base import HORIZONS, QUANTILES, Cache
from .generate import index_ns

Q = np.array(QUANTILES)
Z = norm.ppf(Q)


def pinball(y_n: np.ndarray, qx_n: np.ndarray) -> np.ndarray:
    """Mean pinball loss across the quantile levels, per origin. y_n is (n,), qx_n is (n, Q)."""
    d = y_n[:, None] - qx_n
    return np.maximum(Q[None, :] * d, (Q[None, :] - 1) * d).mean(axis=1)


def newey_west_se(d: np.ndarray, lag: int) -> float:
    d = d - d.mean()
    n = len(d)
    var = float(d @ d) / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * float(d[k:] @ d[:-k]) / n
    return float(np.sqrt(max(var, 0.0) / n))


def dm_test(loss_model: np.ndarray, loss_bench: np.ndarray, h: int) -> tuple[float, float]:
    """Positive statistic: the model's loss is lower. Two-sided normal p-value."""
    d = loss_bench - loss_model
    if len(d) < 30 or d.std() == 0:
        return float("nan"), float("nan")
    se = newey_west_se(d, max(h - 1, 1))
    stat = float(d.mean() / se) if se > 0 else float("nan")
    return stat, float(2 * (1 - norm.cdf(abs(stat))))


def block_bootstrap_ic(x: np.ndarray, y: np.ndarray, block: int, reps: int = 400, seed: int = 0) -> tuple[float, float]:
    n = len(x)
    if n < 30:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    block = max(block, 1)
    starts_n = int(np.ceil(n / block))
    ics = np.empty(reps)
    for b in range(reps):
        idx = np.concatenate([np.arange(s, s + block) % n for s in rng.integers(0, n, starts_n)])[:n]
        ics[b] = spearmanr(x[idx], y[idx]).statistic
    return float(np.nanpercentile(ics, 2.5)), float(np.nanpercentile(ics, 97.5))


def _prepare(cache: Cache, bars: pd.DataFrame) -> pd.DataFrame:
    """Per origin: realised normalised returns, the model's normalised quantiles and the benchmark loss inputs, for every horizon."""
    close = bars["close"].to_numpy(dtype=float)
    ns = index_ns(bars.index)
    pos = pd.Series(np.arange(len(bars)), index=ns)
    o_ns = cache.origins.astype("datetime64[ns]").astype("int64")
    keep = np.isin(o_ns, ns)
    i = pos.loc[o_ns[keep]].to_numpy()
    sigma = daily_vol(bars["close"]).to_numpy()[i]
    rows = {"origin": pd.to_datetime(o_ns[keep], unit="ns", utc=True), "i": i, "sigma": sigma}
    out = pd.DataFrame(rows)
    for j, h in enumerate(HORIZONS):
        ok = i + h < len(close)
        r = np.full(len(i), np.nan)
        r[ok] = np.log(close[i[ok] + h] / close[i[ok]])
        out[f"r{h}"] = r
        for k in range(len(Q)):
            out[f"q{h}_{k}"] = cache.cube[keep][:, j, k]
    return out


def evaluate_model(caches: dict[str, Cache], bars: dict[str, pd.DataFrame], release: pd.Timestamp) -> pd.DataFrame:
    frames = []
    for sym, c in caches.items():
        if c is None or len(c) == 0:
            continue
        f = _prepare(c, bars[sym])
        f["symbol"] = sym
        frames.append(f)
    if not frames:
        return pd.DataFrame()
    allf = pd.concat(frames, ignore_index=True)
    rows = []
    for window, mask in (("all", np.ones(len(allf), bool)), ("post_release", (allf["origin"] >= release).to_numpy())):
        w = allf[mask]
        for h in HORIZONS:
            sd = (w["sigma"] * np.sqrt(h)).to_numpy()
            y = w[f"r{h}"].to_numpy()
            qm = w[[f"q{h}_{k}" for k in range(len(Q))]].to_numpy()
            ok = np.isfinite(sd) & (sd > 0) & np.isfinite(y) & np.isfinite(qm).all(axis=1)
            if ok.sum() < 5:
                rows.append({"window": window, "h": h, "n": int(ok.sum())})
                continue
            w2 = w[ok].assign(sd=sd[ok], y=y[ok] / sd[ok])
            qn = qm[ok] / sd[ok][:, None]
            med = qn[:, int(np.argmin(np.abs(Q - 0.5)))]
            bench = np.broadcast_to(Z, qn.shape)
            l_model, l_bench = pinball(w2["y"].to_numpy(), qn), pinball(w2["y"].to_numpy(), bench)
            l_loc = pinball(w2["y"].to_numpy(), med[:, None] + Z[None, :])
            by_date = pd.DataFrame({"d": w2["origin"].to_numpy(), "m": l_model, "b": l_bench}).groupby("d").mean().sort_index()
            dm_stat, dm_p = dm_test(by_date["m"].to_numpy(), by_date["b"].to_numpy(), h)
            order = np.argsort(w2["origin"].to_numpy(), kind="stable")
            if np.ptp(med) < 1e-12:                    # a constant median (a zero-drift forecast) carries no direction information: IC is 0, not undefined
                ic, lo, hi = 0.0, 0.0, 0.0
            else:
                ic = float(spearmanr(med, w2["y"].to_numpy()).statistic)
                lo, hi = block_bootstrap_ic(med[order], w2["y"].to_numpy()[order], h)
            nz = w2["y"].to_numpy() != 0
            up = float((w2["y"].to_numpy() > 0).mean())
            rows.append({
                "window": window, "h": h, "n": int(ok.sum()), "from": w2["origin"].min(), "to": w2["origin"].max(),
                "skill": 1 - l_model.mean() / l_bench.mean(), "location_skill": 1 - l_loc.mean() / l_bench.mean(),
                "ic": ic, "ic_lo": lo, "ic_hi": hi,
                "hit": float((np.sign(med[nz]) == np.sign(w2["y"].to_numpy()[nz])).mean()), "up_rate": up,
                "cov80": float(((w2["y"].to_numpy() >= qn[:, 0]) & (w2["y"].to_numpy() <= qn[:, -1])).mean()),
                "cov40": float(((w2["y"].to_numpy() >= qn[:, 1]) & (w2["y"].to_numpy() <= qn[:, 3])).mean()),
                "dm_stat": dm_stat, "dm_p": dm_p,
            })
    return pd.DataFrame(rows)


def verdict(res: pd.DataFrame) -> str:
    """A deliberately blunt reading, using only the post-release window at the longer horizons."""
    post = res[(res["window"] == "post_release") & (res["h"] >= 5)] if len(res) else res
    if post.empty or post["skill"].isna().all():
        return "not enough post-release data to judge"
    better = post[(post["skill"] > 0) & (post["dm_p"] < 0.05)]
    if len(better) and (post["ic_lo"] > 0).any():
        return "shows skill versus a random walk after release (still needs forward confirmation)"
    if len(better):
        return "better loss than a random walk after release, but no reliable direction information"
    return "no skill versus a random walk after release"
