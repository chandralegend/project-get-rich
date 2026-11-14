"""Vectorised daily backtest for a target-position series.

Timing: `target[t]` is decided at the CLOSE of day t using data up to t. The position it creates is
held over the NEXT day's return. Trading cost is charged on the traded fraction at the cost model's
one-way rate and is deducted from that same next-day return.

Cost control: a rebalance happens only if the target moved by at least `band` of equity, or the target
is flat while a position is open. This no-trade band is a standard way to stop vol-scaling from paying
costs on tiny daily adjustments.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import CostModel


def run(close: pd.Series, target: pd.Series, cost: CostModel | None = None, band: float = 0.0) -> pd.DataFrame:
    cost = cost or CostModel()
    close = close.astype(float)
    tgt = target.reindex(close.index).fillna(0.0).to_numpy()
    n = len(close)
    pos = np.zeros(n)
    prev = 0.0
    for t in range(n):
        want = tgt[t]
        if abs(want - prev) >= band and want != prev or (want == 0.0 and prev != 0.0):
            prev = want
        pos[t] = prev
    traded = np.abs(np.diff(pos, prepend=0.0))
    ret = close.pct_change().fillna(0.0).to_numpy()
    held = np.concatenate([[0.0], pos[:-1]])          # position carried into day t
    gross = held * ret
    cost_paid = np.concatenate([[0.0], traded[:-1]]) * cost.one_way()   # trades made at the previous close
    df = pd.DataFrame(
        {"position": held, "gross": gross, "cost": cost_paid, "net": gross - cost_paid,
         "turnover": np.concatenate([[0.0], traded[:-1]])},
        index=close.index,
    )
    return df
