"""Persistence and portfolio state for the order path. Orders, fills and equity snapshots live in DuckDB; state is replayed from fills.

Never call connect() while already inside a connect() block (the lock is not re-entrant).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from .. import config
from ..ids import new_id
from ..obs.events import utcnow
from ..store.db import connect
from . import limits as L
from .types import FillInfo, PortfolioState, Position

TF_SECONDS = {"1h": 3600, "1d": 86400}


def start_equity() -> float:
    return float(os.environ.get("GETRICH_PAPER_EQUITY", "500"))


def kill_path():
    return config.state_dir() / "KILL"


def is_killed() -> bool:
    return kill_path().exists()


def halt_path():
    return config.state_dir() / "HALT"


def is_halted() -> bool:
    return halt_path().exists()


def replay(fills: list[tuple], order_meta: dict[str, tuple], cash0: float) -> tuple[float, dict[str, Position], float, float]:
    """fills: (order_id, ts, symbol, side, qty, price, fee) in time order. Returns (cash, open positions, realized pnl, fees paid)."""
    cash, positions, realized, fees = cash0, {}, 0.0, 0.0
    for order_id, ts, symbol, side, qty, price, fee in fills:
        fees += fee
        pos = positions.get(symbol)
        if side == "buy":
            cash -= qty * price + fee
            if pos is None:
                stop, tp = order_meta.get(order_id, (None, None))
                positions[symbol] = Position(symbol, qty, price, stop, tp, order_id, ts)
            else:
                pos.avg_price = (pos.avg_price * pos.qty + price * qty) / (pos.qty + qty)
                pos.qty += qty
        else:
            cash += qty * price - fee
            if pos is not None:
                realized += (price - pos.avg_price) * qty - fee
                pos.qty -= qty
                if pos.qty <= 1e-12:
                    del positions[symbol]
    return cash, positions, realized, fees


def latest_prices(con, symbols, now: datetime, venue: str = "binance") -> dict[str, tuple[float, float, str]]:
    out = {}
    for sym in symbols:
        best = None
        for tf in ("1h", "1d"):
            row = con.execute("SELECT ts_open, close FROM bars WHERE venue = ? AND symbol = ? AND timeframe = ? ORDER BY ts_open DESC LIMIT 1", [venue, sym, tf]).fetchone()
            if row:
                age = (now - row[0]).total_seconds() - TF_SECONDS[tf]          # time since that bar closed
                if best is None or age < best[1]:
                    best = (float(row[1]), max(age, 0.0), tf)
        if best:
            out[sym] = best
    return out


def load_state(symbols, now: datetime | None = None, venue: str = "paper") -> PortfolioState:
    now = now or utcnow()
    with connect() as con:
        fills = con.execute("SELECT order_id, ts, symbol, side, qty, price, fee FROM fills WHERE venue = ? ORDER BY ts, fill_id", [venue]).fetchall()
        meta = {r[0]: (r[1], r[2]) for r in con.execute("SELECT order_id, stop_price, take_profit FROM orders WHERE venue = ?", [venue]).fetchall()}
        held = {f[2] for f in fills}
        prices = latest_prices(con, set(symbols) | held, now)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        snaps = con.execute("SELECT ts, equity FROM equity_snapshots WHERE venue = ? ORDER BY ts", [venue]).fetchall()
        day_ago = now - timedelta(hours=24)
        cancels = con.execute("SELECT count(*) FROM orders WHERE venue = ? AND status = 'cancelled' AND updated_at >= ?", [venue, day_ago]).fetchone()[0]
        n_fills = con.execute("SELECT count(*) FROM fills WHERE venue = ? AND ts >= ?", [venue, day_ago]).fetchone()[0]
    cash, positions, _realized, _fees = replay(fills, meta, start_equity())
    equity = cash + sum(p.qty * prices.get(p.symbol, (p.avg_price, 0, ""))[0] for p in positions.values())
    peak = max([start_equity(), equity] + [e for _t, e in snaps])
    before_today = [e for t, e in snaps if t < today]
    day_start = before_today[-1] if before_today else start_equity()
    lim, why = L.load()
    return PortfolioState(now=now, equity=equity, cash=cash, peak_equity=peak, day_start_equity=day_start, positions=positions, prices=prices,
                          killed=is_killed(), halt_latched=is_halted(), limits_ok=lim is not None, limits_detail=why, cancels_24h=cancels, fills_24h=n_fills)


def snapshot(state: PortfolioState, venue: str = "paper") -> None:
    with connect() as con:
        con.execute("INSERT INTO equity_snapshots VALUES (?,?,?,?,?)", [state.now, venue, state.equity, state.cash, state.exposure])


def insert_order(order_id: str, intent, venue: str, status: str, qty: float, ref_price: float | None, verdict: dict, now: datetime) -> None:
    with connect() as con:
        con.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [order_id, intent.decision_id, now, now, venue, intent.symbol, intent.side.lower(), status, qty, ref_price,
                     intent.stop_price, intent.take_profit, intent.source, intent.reason[:300], json.dumps(verdict), ""])


def set_status(order_id: str, status: str, now: datetime, detail: str = "", qty: float | None = None) -> None:
    with connect() as con:
        if qty is None:
            con.execute("UPDATE orders SET status = ?, updated_at = ?, detail = ? WHERE order_id = ?", [status, now, detail[:300], order_id])
        else:
            con.execute("UPDATE orders SET status = ?, updated_at = ?, detail = ?, qty = ? WHERE order_id = ?", [status, now, detail[:300], qty, order_id])


def get_order(order_id: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM orders WHERE order_id = ?", [order_id]).fetchone()
        cols = [d[0] for d in con.description]
    return dict(zip(cols, row)) if row else None


def record_fills(order_id: str, symbol: str, side: str, fills: list[FillInfo], venue: str) -> None:
    with connect() as con:
        for f in fills:
            con.execute("INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?)", [new_id("f"), order_id, f.ts, venue, symbol, side, f.qty, f.price, f.fee, f.kind])


def list_orders(limit: int = 20, venue: str | None = None) -> list[dict]:
    with connect() as con:
        q = "SELECT order_id, created_at, venue, symbol, side, status, qty, ref_price, stop_price, source, reason, detail FROM orders"
        rows = con.execute(q + (" WHERE venue = ?" if venue else "") + " ORDER BY created_at DESC LIMIT ?", ([venue] if venue else []) + [limit]).fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def realized_summary(venue: str = "paper") -> dict:
    with connect() as con:
        fills = con.execute("SELECT order_id, ts, symbol, side, qty, price, fee FROM fills WHERE venue = ? ORDER BY ts, fill_id", [venue]).fetchall()
    _cash, _pos, realized, fees = replay(fills, {}, start_equity())
    return {"realized_pnl": realized, "fees_paid": fees, "fills": len(fills)}
