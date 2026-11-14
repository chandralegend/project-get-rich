"""Features and the pooled triple-barrier dataset for the PI-Net v1 (market and forecast channels).

Every feature at decision day t uses only data up to the close of day t. Channels:
  market    price, volatility, range, volume and trend measures from daily bars
  forecast  the HAR-RV volatility forecast and how it compares with simpler estimates
  context   which asset, and day of week
The Chronos-2 / TimesFM quantile forecasts named in ARCHITECTURE.md 4.3 are NOT included yet: the research found
they do not beat a random walk on returns, and they need large model downloads. They can be added as a channel later.

One row is one candidate long trade (a decision at a day's close, labelled by the triple-barrier rule with costs).
Rows from BTC and ETH are pooled and sorted by decision time so the purged splitters work.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import baselines, har, labels
from .costs import CostModel
from .data import load_bars

MARKET = [
    "ret_1", "ret_2", "ret_5", "ret_10", "ret_20", "ret_60",
    "mom_20_vol", "mom_60_vol", "vol_20", "vol_60", "vol_ewma",
    "range_1", "range_10", "dist_ema_16", "dist_ema_64", "dist_ema_256",
    "drawdown_90", "volume_z", "trend_votes",
]
FORECAST = ["har_vol", "har_vs_ewma", "har_vs_real20"]
CONTEXT = ["is_eth", "dow_sin", "dow_cos"]
CHANNELS = {"market": MARKET, "forecast": FORECAST, "context": CONTEXT}
ALL = MARKET + FORECAST + CONTEXT


def market_features(daily: pd.DataFrame) -> pd.DataFrame:
    c, h, l = daily["close"], daily["high"], daily["low"]
    r1 = c.pct_change()
    f = pd.DataFrame(index=daily.index)
    for n in (1, 2, 5, 10, 20, 60):
        f[f"ret_{n}"] = c.pct_change(n)
    vol60 = r1.rolling(60).std()
    f["vol_20"], f["vol_60"] = r1.rolling(20).std(), vol60
    f["vol_ewma"] = np.sqrt((r1**2).ewm(alpha=0.06, adjust=False, min_periods=20).mean())
    f["mom_20_vol"], f["mom_60_vol"] = f["ret_20"] / (vol60 * np.sqrt(20)), f["ret_60"] / (vol60 * np.sqrt(60))
    rng = (h - l) / c
    f["range_1"], f["range_10"] = rng, rng.rolling(10).mean()
    for n in (16, 64, 256):
        f[f"dist_ema_{n}"] = c / c.ewm(span=n, adjust=False, min_periods=n).mean() - 1
    f["drawdown_90"] = c / c.rolling(90).max() - 1
    lv = np.log(daily["volume"].replace(0, np.nan))
    f["volume_z"] = (lv - lv.rolling(20).mean()) / lv.rolling(20).std()
    f["trend_votes"] = baselines.trend_signal(c)
    return f[MARKET]


def forecast_features(daily: pd.DataFrame, har_vol_annual: pd.Series) -> pd.DataFrame:
    c = daily["close"]
    ewma = baselines.ewma_vol(c)
    real20 = c.pct_change().rolling(20).std() * np.sqrt(365)
    f = pd.DataFrame(index=daily.index)
    f["har_vol"] = har_vol_annual.reindex(daily.index)
    f["har_vs_ewma"] = np.log(f["har_vol"] / ewma)
    f["har_vs_real20"] = np.log(f["har_vol"] / real20)
    return f[FORECAST]


@dataclass
class Dataset:
    X: np.ndarray                 # n x len(ALL), float32
    y: np.ndarray                 # 1 if r_net > 0
    r_net: np.ndarray             # outcome in R at the base cost model
    r_gross: np.ndarray
    cost_r: np.ndarray            # round-trip cost in R for each row
    t0: np.ndarray                # decision time (datetime64[ns])
    t1: np.ndarray                # label resolution time
    asset: np.ndarray             # symbol per row
    bar: pd.DatetimeIndex         # daily bar open time of the decision
    aux: np.ndarray               # n x 2 dense targets: next-day return in sigma units, next-day log RV (NaN if unknown)
    columns: list[str] = field(default_factory=lambda: list(ALL))
    channels: dict[str, list[str]] = field(default_factory=lambda: dict(CHANNELS))

    def __len__(self) -> int:
        return len(self.y)

    def r_at(self, cost_multiple: float) -> np.ndarray:
        """Outcomes re-priced at a different cost level (2.0 = the 2x stress)."""
        return self.r_gross - cost_multiple * self.cost_r

    def channel_idx(self, name: str) -> list[int]:
        return [self.columns.index(c) for c in self.channels[name]]


def build_symbol_frame(symbol: str, daily: pd.DataFrame, hourly: pd.DataFrame, cost: CostModel, *,
                       tp_mult: float = 2.0, sl_mult: float = 1.0, horizon: int = 10,
                       primary_min_votes: float | None = None) -> pd.DataFrame:
    rv = har.daily_rv_from_hourly(hourly)
    har_vol = np.sqrt(har.har_forecast(rv) * 365).reindex(daily.index)
    feats = pd.concat([market_features(daily), forecast_features(daily, har_vol)], axis=1)
    feats["is_eth"] = 1.0 if symbol.startswith("ETH") else 0.0
    dow = daily.index.day_of_week.to_numpy()
    feats["dow_sin"], feats["dow_cos"] = np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)

    sigma = labels.daily_vol(daily["close"])
    lab = labels.triple_barrier(daily, sigma, tp_mult=tp_mult, sl_mult=sl_mult, horizon=horizon, cost=cost)
    lab["bar"] = lab["t0"] - pd.Timedelta(days=1)
    lab = lab.set_index("bar")
    ret_next = daily["close"].pct_change().shift(-1) / sigma
    lab["aux_ret"] = ret_next.clip(-5, 5).reindex(lab.index)
    lab["aux_rv"] = np.log(rv.shift(-1).reindex(lab.index))
    out = lab.join(feats[ALL], how="inner")
    out["asset"] = symbol
    out = out.dropna(subset=ALL)
    if primary_min_votes is not None:   # meta-labelling: keep only the days the primary (trend) rule says long
        out = out[out["trend_votes"] >= primary_min_votes - 1e-9]
    return out


def make_dataset(symbols=("BTCUSDT", "ETHUSDT"), cost: CostModel | None = None, **kw) -> Dataset:
    cost = cost or CostModel()
    frames = [build_symbol_frame(s, load_bars(s, "1d"), load_bars(s, "1h"), cost, **kw) for s in symbols]
    return from_frames(frames)


def from_frames(frames: list[pd.DataFrame]) -> Dataset:
    df = pd.concat(frames).reset_index().rename(columns={"index": "bar"})
    df = df.sort_values(["t0", "asset"], kind="stable").reset_index(drop=True)
    return Dataset(
        X=df[ALL].to_numpy(dtype=np.float32),
        y=df["label"].to_numpy(dtype=int),
        r_net=df["r_net"].to_numpy(dtype=float),
        r_gross=df["r_gross"].to_numpy(dtype=float),
        cost_r=df["cost_r"].to_numpy(dtype=float),
        t0=df["t0"].to_numpy(dtype="datetime64[ns]"),
        t1=df["t1"].to_numpy(dtype="datetime64[ns]"),
        asset=df["asset"].to_numpy(),
        bar=pd.DatetimeIndex(df["bar"]),
        aux=df[["aux_ret", "aux_rv"]].to_numpy(dtype=float),
    )
