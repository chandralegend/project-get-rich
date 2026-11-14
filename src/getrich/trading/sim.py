"""SimBroker: paper trading that is deliberately pessimistic. Fills pay the project cost model's fee and slippage,
and a stop that is touched fills at the stop (or at the open, if the bar gapped through it). If one bar touches both
stop and take profit, the stop is assumed to have been hit first.
"""

from __future__ import annotations

from datetime import datetime

from ..eval.costs import CostModel
from ..obs.events import utcnow
from ..store.db import connect
from .types import Broker, FillInfo, Position


class SimBroker(Broker):
    venue = "paper"

    def __init__(self, costs: CostModel | None = None):
        self.costs = costs or CostModel()

    def _fee(self, notional: float) -> float:
        return notional * self.costs.fee_bps / 1e4

    def buy(self, symbol, qty, ref_price, stop, take_profit, client_id):
        price = ref_price * (1 + self.costs.slippage_bps / 1e4)
        return [FillInfo(price, qty, self._fee(price * qty), utcnow(), "entry")]

    def sell(self, symbol, qty, ref_price, kind, client_id):
        price = ref_price * (1 - self.costs.slippage_bps / 1e4)
        return [FillInfo(price, qty, self._fee(price * qty), utcnow(), kind)]

    def exit_fill(self, pos: Position, kind: str, price: float, ts: datetime) -> FillInfo:
        px = price * (1 - self.costs.slippage_bps / 1e4)
        return FillInfo(px, pos.qty, self._fee(px * pos.qty), ts, kind)

    def poll_exits(self, positions, now):
        """Look at stored bars since each position's entry fill for a touched stop or take profit."""
        out = []
        for sym, pos in positions.items():
            if pos.stop_price is None and pos.take_profit is None:
                continue
            with connect() as con:
                entry_ts = con.execute("SELECT min(ts) FROM fills WHERE order_id = ? AND side = 'buy'", [pos.order_id]).fetchone()[0]
                tf = "1h" if con.execute("SELECT 1 FROM bars WHERE symbol = ? AND timeframe = '1h' LIMIT 1", [sym]).fetchone() else "1d"
                bars = con.execute("SELECT ts_open, open, high, low FROM bars WHERE venue = 'binance' AND symbol = ? AND timeframe = ? AND ts_open >= ? ORDER BY ts_open",
                                   [sym, tf, entry_ts]).fetchall()
            for ts_open, o, h, l in bars:
                if pos.stop_price is not None and l <= pos.stop_price:
                    out.append((sym, self.exit_fill(pos, "stop", min(pos.stop_price, o), ts_open)))
                    break
                if pos.take_profit is not None and h >= pos.take_profit:
                    out.append((sym, self.exit_fill(pos, "take_profit", max(pos.take_profit, 0) if o < pos.take_profit else o, ts_open)))
                    break
        return out
