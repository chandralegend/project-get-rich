"""Load stored bars as pandas frames indexed by UTC bar-open time."""

from __future__ import annotations

import pandas as pd

from ..store.db import connect


def load_bars(symbol: str, timeframe: str = "1d", venue: str = "binance") -> pd.DataFrame:
    with connect() as con:
        df = con.execute(
            "SELECT ts_open, open, high, low, close, volume FROM bars "
            "WHERE venue = ? AND symbol = ? AND timeframe = ? ORDER BY ts_open",
            [venue, symbol, timeframe],
        ).df()
    if df.empty:
        raise ValueError(f"no {timeframe} bars stored for {venue}:{symbol}")
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True)
    return df.set_index("ts_open")
