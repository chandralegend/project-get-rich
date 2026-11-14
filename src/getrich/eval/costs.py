"""Transaction cost model. Every backtest, label and decision rule in the project uses this one object.

The defaults are ASSUMPTIONS, not measured numbers: 10 bps fee per side is the standard Binance spot
rate as I understand it (not verified against the current fee schedule), and 5 bps slippage per side is
deliberately conservative for BTC and ETH at small size. Replace them with measured values after
micro-live trading (ARCHITECTURE.md, Phase 6). Results must also be shown at `stressed()` costs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    fee_bps: float = 10.0       # per side
    slippage_bps: float = 5.0   # per side

    def one_way(self) -> float:
        """Cost of one trade (entry or exit) as a fraction of the traded notional."""
        return (self.fee_bps + self.slippage_bps) / 1e4

    def round_trip(self) -> float:
        return 2 * self.one_way()

    def stressed(self, multiple: float = 2.0) -> "CostModel":
        return CostModel(self.fee_bps * multiple, self.slippage_bps * multiple)

    def cost_in_r(self, stop_fraction: float) -> float:
        """Round-trip cost expressed in R, where 1R is the stop distance as a fraction of price."""
        if stop_fraction <= 0:
            raise ValueError("stop_fraction must be positive")
        return self.round_trip() / stop_fraction
