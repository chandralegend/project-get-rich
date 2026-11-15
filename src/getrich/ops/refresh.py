"""One call that brings market data up to date for the instruments in scope: Binance for crypto, Yahoo for forex and metals.

Collectors run one after another, never in parallel: they all write the one DuckDB file, and parallel backfills were seen to time out on its lock.
"""

from __future__ import annotations

from ..collectors import binance, yahoo
from ..obs.events import emit
from ..trading import instruments

SERVICE = "ops.refresh"


def run(classes: tuple[str, ...] | None = None) -> dict:
    classes = tuple(classes) if classes else ("crypto", "fx", "metal")
    out, ok = {}, True
    if "crypto" in classes:
        symbols = instruments.symbols("crypto")
        for tf in ("1d", "1h"):
            tf_ok, summary = binance.collect(symbols, tf)
            ok = ok and tf_ok
            out[f"binance/{tf}"] = sum(summary.values())
    fx = [i.symbol for i in instruments.INSTRUMENTS if i.asset_class in classes and i.source == "yahoo"]
    if fx:
        fx_ok, summary = yahoo.collect(fx, ["1d", "1h"])
        ok = ok and fx_ok
        out["yahoo"] = sum(summary.values())
    emit("ops.refresh", service=SERVICE, ok=ok, rows_added=out, classes=list(classes))
    return {"ok": ok, "rows_added": out}
