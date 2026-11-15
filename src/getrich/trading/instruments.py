"""The tradable universe: what each instrument is, where its bars come from, what it costs, and when its market is open.

Crypto comes from Binance spot (public klines). Forex, gold and silver come from Yahoo Finance's public chart endpoint (see collectors/yahoo.py).
Everything is quoted in US dollars so profit and loss need no currency conversion. Pairs whose real quote is another currency are stored as the
INVERSE series, named after the currency you are buying: JPYUSD is 1 / USDJPY, so going long JPYUSD is going short USDJPY (and likewise CAD and CHF).
Gold and silver are CME futures prices (GC=F, SI=F) used as proxies for spot, which Yahoo does not carry.

Costs are ASSUMPTIONS until micro-live: per side, a fee plus slippage (for forex the fee is zero and the slippage stands for half the spread plus a
little). Overnight financing, swaps and rollover are not modelled, which flatters anything held across days, mostly in forex.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..eval.costs import CostModel
from .types import DEFAULT_RULES, SymbolRules


@dataclass(frozen=True)
class Instrument:
    symbol: str                 # our canonical name; also the key in bars and orders
    name: str
    asset_class: str            # crypto | fx | metal
    source: str                 # the `venue` its bars are stored under: binance | yahoo
    provider_symbol: str        # the symbol at the data provider
    cost: CostModel
    invert: bool = False        # store 1 / price (USD-base pairs)
    core: bool = False          # always shown in full detail to the trader
    note: str = ""


def _crypto(sym: str, name: str, bps_slip: float = 5.0, core: bool = False) -> Instrument:
    return Instrument(sym, name, "crypto", "binance", sym, CostModel(10.0, bps_slip), core=core)


def _fx(sym: str, name: str, provider: str, slip_bps: float, invert: bool = False, note: str = "") -> Instrument:
    return Instrument(sym, name, "fx", "yahoo", provider, CostModel(0.0, slip_bps), invert=invert, note=note)


INSTRUMENTS: tuple[Instrument, ...] = (
    _crypto("BTCUSDT", "Bitcoin", core=True), _crypto("ETHUSDT", "Ethereum", core=True),
    _crypto("SOLUSDT", "Solana", 8.0), _crypto("BNBUSDT", "BNB", 8.0), _crypto("XRPUSDT", "XRP", 8.0), _crypto("ADAUSDT", "Cardano", 8.0),
    _crypto("DOGEUSDT", "Dogecoin", 8.0), _crypto("LINKUSDT", "Chainlink", 8.0), _crypto("AVAXUSDT", "Avalanche", 8.0), _crypto("LTCUSDT", "Litecoin", 8.0),
    _fx("EURUSD", "Euro / US dollar", "EURUSD=X", 1.0), _fx("GBPUSD", "Pound / US dollar", "GBPUSD=X", 1.5),
    _fx("AUDUSD", "Australian dollar / US dollar", "AUDUSD=X", 1.8), _fx("NZDUSD", "New Zealand dollar / US dollar", "NZDUSD=X", 2.2),
    _fx("JPYUSD", "Yen in US dollars (inverse of USDJPY: long = short USDJPY)", "USDJPY=X", 1.8, invert=True),
    _fx("CADUSD", "Canadian dollar in US dollars (inverse of USDCAD: long = short USDCAD)", "USDCAD=X", 2.0, invert=True),
    _fx("CHFUSD", "Swiss franc in US dollars (inverse of USDCHF: long = short USDCHF)", "USDCHF=X", 2.2, invert=True),
    Instrument("XAUUSD", "Gold (CME futures proxy)", "metal", "yahoo", "GC=F", CostModel(0.0, 2.5), note="futures price; rolls between contracts"),
    Instrument("XAGUSD", "Silver (CME futures proxy)", "metal", "yahoo", "SI=F", CostModel(0.0, 6.0), note="futures price; rolls between contracts"),
)
BY_SYMBOL = {i.symbol: i for i in INSTRUMENTS}
assert set(BY_SYMBOL) <= set(DEFAULT_RULES), "every instrument needs symbol rules"


def get(symbol: str) -> Instrument | None:
    return BY_SYMBOL.get(symbol)


def symbols(asset_class: str | None = None) -> list[str]:
    return [i.symbol for i in INSTRUMENTS if asset_class is None or i.asset_class == asset_class]


def cost_for(symbol: str) -> CostModel:
    i = BY_SYMBOL.get(symbol)
    return i.cost if i else CostModel()


def rules_for(symbol: str) -> SymbolRules | None:
    return DEFAULT_RULES.get(symbol)


def bar_venue(symbol: str) -> str:
    i = BY_SYMBOL.get(symbol)
    return i.source if i else "binance"


def is_open(symbol: str, now: datetime) -> bool:
    """Crypto trades all the time. Forex and metals close for the weekend: roughly Friday 22:00 UTC to Sunday 22:00 UTC."""
    i = BY_SYMBOL.get(symbol)
    if i is None or i.asset_class == "crypto":
        return True
    wd, h = now.weekday(), now.hour               # Monday is 0
    if wd == 5:
        return False
    if wd == 4 and h >= 22:
        return False
    if wd == 6 and h < 22:
        return False
    return True
