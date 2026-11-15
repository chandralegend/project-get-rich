"""Plain data types for the order path. No I/O here, so the risk gate stays a pure function."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..ids import new_id


@dataclass(frozen=True)
class SymbolRules:
    """Exchange filters for a symbol. Defaults below are ASSUMPTIONS for paper trading; the testnet adapter reads the real ones."""
    step: float          # LOT_SIZE stepSize
    tick: float          # PRICE_FILTER tickSize
    min_qty: float
    min_notional: float  # smallest order value in the quote currency
    min_stop_fraction: float = 0.005   # stops tighter than this share of price are noise for this instrument


DEFAULT_RULES = {
    "BTCUSDT": SymbolRules(step=1e-5, tick=0.01, min_qty=1e-5, min_notional=5.0),
    "ETHUSDT": SymbolRules(step=1e-4, tick=0.01, min_qty=1e-4, min_notional=5.0),
    # More Binance spot pairs. ASSUMED filters for paper trading (the testnet adapter reads the real ones).
    "SOLUSDT": SymbolRules(step=1e-3, tick=0.01, min_qty=1e-3, min_notional=5.0),
    "BNBUSDT": SymbolRules(step=1e-3, tick=0.01, min_qty=1e-3, min_notional=5.0),
    "XRPUSDT": SymbolRules(step=0.1, tick=1e-4, min_qty=0.1, min_notional=5.0),
    "ADAUSDT": SymbolRules(step=0.1, tick=1e-4, min_qty=0.1, min_notional=5.0),
    "DOGEUSDT": SymbolRules(step=1.0, tick=1e-5, min_qty=1.0, min_notional=5.0),
    "LINKUSDT": SymbolRules(step=0.01, tick=0.001, min_qty=0.01, min_notional=5.0),
    "AVAXUSDT": SymbolRules(step=0.01, tick=0.01, min_qty=0.01, min_notional=5.0),
    "LTCUSDT": SymbolRules(step=1e-3, tick=0.01, min_qty=1e-3, min_notional=5.0),
    # Forex and metals, quoted in US dollars. ASSUMED 1-unit granularity (OANDA-style); many cTrader brokers set 0.01 lot = 1,000 units as the minimum,
    # which at a few hundred dollars would need leverage. Stops can be tighter than in crypto because the instruments move less.
    "EURUSD": SymbolRules(step=1.0, tick=1e-5, min_qty=1.0, min_notional=1.0, min_stop_fraction=0.0015),
    "GBPUSD": SymbolRules(step=1.0, tick=1e-5, min_qty=1.0, min_notional=1.0, min_stop_fraction=0.0015),
    "AUDUSD": SymbolRules(step=1.0, tick=1e-5, min_qty=1.0, min_notional=1.0, min_stop_fraction=0.0015),
    "NZDUSD": SymbolRules(step=1.0, tick=1e-5, min_qty=1.0, min_notional=1.0, min_stop_fraction=0.0015),
    "JPYUSD": SymbolRules(step=1.0, tick=1e-7, min_qty=1.0, min_notional=1.0, min_stop_fraction=0.0015),
    "CADUSD": SymbolRules(step=1.0, tick=1e-5, min_qty=1.0, min_notional=1.0, min_stop_fraction=0.0015),
    "CHFUSD": SymbolRules(step=1.0, tick=1e-5, min_qty=1.0, min_notional=1.0, min_stop_fraction=0.0015),
    "XAUUSD": SymbolRules(step=0.01, tick=0.01, min_qty=0.01, min_notional=1.0, min_stop_fraction=0.003),
    "XAGUSD": SymbolRules(step=0.01, tick=0.001, min_qty=0.01, min_notional=1.0, min_stop_fraction=0.004),
}


@dataclass
class OrderIntent:
    """What someone (or later a model) wants to do. It is only a request: the risk gate decides what, if anything, may happen."""
    symbol: str
    side: str                                   # "buy" / "sell" (spot, long only: a sell only reduces a long). Margin: "short" opens a short, "cover" reduces one.
    stop_price: float | None = None             # required for a buy
    take_profit: float | None = None
    qty: float | None = None                    # None: size from the risk budget. The gate may only reduce it, never raise it.
    risk_fraction: float | None = None          # may only lower the default risk per trade, never raise it
    expected_edge_fraction: float | None = None  # expected gross move as a fraction of price, if the source claims one
    source: str = "manual"
    reason: str = ""
    decision_id: str = field(default_factory=lambda: new_id("d"))


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float
    stop_price: float | None
    take_profit: float | None
    order_id: str
    entry_ts: datetime | None = None
    side: str = "long"                          # "long" or "short"; qty is always positive


@dataclass
class PortfolioState:
    now: datetime
    equity: float
    cash: float
    peak_equity: float
    day_start_equity: float
    positions: dict[str, Position]
    prices: dict[str, tuple[float, float, str]]   # symbol -> (last price, age in seconds, bar timeframe)
    killed: bool = False
    halt_latched: bool = False       # set when the drawdown halt tripped; only the owner clears it
    limits_ok: bool = True
    limits_detail: str = ""
    cancels_24h: int = 0
    fills_24h: int = 0

    @property
    def exposure(self) -> float:
        return sum(p.qty * self.prices.get(p.symbol, (p.avg_price, 0, ""))[0] for p in self.positions.values())


@dataclass
class Verdict:
    approved: bool
    qty: float = 0.0
    notional: float = 0.0
    risk_amount: float = 0.0
    risk_fraction: float = 0.0
    reasons: list[str] = field(default_factory=list)       # why it was rejected or reduced
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    halted: bool = False
    leverage_after: float = 0.0          # gross exposure over equity once this order fills
    liq_distance: float = 0.0            # adverse move, as a fraction of price, that would liquidate the account (cross margin estimate)

    def to_dict(self) -> dict:
        return {"approved": self.approved, "qty": self.qty, "notional": round(self.notional, 2), "risk_amount": round(self.risk_amount, 4),
                "risk_fraction": round(self.risk_fraction, 5), "leverage_after": round(self.leverage_after, 3), "liq_distance": round(self.liq_distance, 4), "reasons": self.reasons, "halted": self.halted,
                "checks": [{"check": n, "ok": ok, "detail": d} for n, ok, d in self.checks]}


@dataclass
class FillInfo:
    price: float
    qty: float
    fee: float                 # in the quote currency
    ts: datetime
    kind: str                  # entry | exit | stop | take_profit | flatten
    venue_ref: str = ""        # the venue's own order id, when there is one


class Broker:
    """Interface every venue implements (SimBroker now, BinanceTestnetBroker next, cTrader and MT5 later)."""
    venue = "?"

    def symbol_rules(self):
        """Exchange filters per symbol, or None to use the paper defaults."""
        return None

    def buy(self, symbol: str, qty: float, ref_price: float, stop: float, take_profit: float | None, client_id: str) -> list[FillInfo]:
        raise NotImplementedError

    def sell(self, symbol: str, qty: float, ref_price: float, kind: str, client_id: str) -> list[FillInfo]:
        raise NotImplementedError

    def poll_exits(self, positions: dict[str, Position], now: datetime) -> list[tuple[str, FillInfo]]:
        """Protective exits (stop or take profit) that have happened since the last look, as (symbol, fill)."""
        raise NotImplementedError
