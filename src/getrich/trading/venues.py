"""Broker factory. `paper` is the local simulator; `testnet` is Binance Spot Testnet (virtual money). There is no live venue yet."""

from __future__ import annotations

from .types import Broker

VENUES = ("paper", "testnet")


def get_broker(venue: str) -> Broker:
    if venue == "paper":
        from .sim import SimBroker

        return SimBroker()
    if venue == "testnet":
        from .binance_testnet import BinanceTestnetBroker

        return BinanceTestnetBroker()
    raise ValueError(f"unknown venue {venue!r}; choose from {VENUES}")
