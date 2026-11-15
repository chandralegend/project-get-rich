# Shorting and leverage in the order path (replay only)

Added 2026-11-15 at the owner's request ("should work more like a day trader, should take risks"). Status: built into the risk gate and a replay engine; **not wired into paper or testnet trading**, and nothing has been run against an exchange.

## What changed

- `config/limits.toml` may carry `max_leverage` (1 to 10, default 1 = spot-equivalent) and `allow_short` (default false). `max_exposure_fraction` is gross notional over equity and may exceed 1 only up to `max_leverage`. Both are part of the pinned hash; changing them is the owner's approval (`limits-approve --max-leverage 3 --max-exposure 3 --allow-short`). The pinned file today is unchanged: spot, long-only.
- The gate accepts `short` (open a short) and `cover` (reduce one). A cover is reduce-only and always allowed, like a sell, including when halted, killed, or with shorting switched off. A short needs `allow_short`. A sell cannot close a short and a cover cannot close a long. One position per symbol, no adding, unchanged.
- Sizing in a margin account is the smallest of: risk budget, exposure cap, free margin (equity minus exposure over leverage), a liquidation buffer, and any requested size. The buffer says the stop must sit inside half the distance to liquidation (`LIQ_SAFETY`), with liquidation at equity falling to 0.5% (`MAINTENANCE_MARGIN`, assumed) of gross exposure. The verdict reports leverage after the fill and the distance to liquidation.
- `service.propose` refuses `short` and `cover` for now (the book, SimBroker and testnet adapter are spot): it fails closed instead of mis-accounting a short.
- `trading/replay_futures.py` replays hourly bars through that gate with a margin account: fees and slippage per side, funding every 8 hours (assumed 0.01%), gaps through stops fill at the open, liquidation at the worst price of a bar. Its account model is written at the top of the file.

## What the cost model already says about day trading

Round-trip cost is 30 bps and the cost gate allows at most 0.25R, so stops under about 1.2% are refused. Tighter, scalping-style stops cannot pass the gate with these costs. That is a property of the costs, not a bug. Real costs are still assumptions until micro-live.

## Still needed before any of this could go live

A margin broker (Binance futures testnet adapter, margin and funding in the book), real funding history (a download that needs the owner's approval), the owner's explicit approval of leverage and shorting in `limits.toml`, and a testnet run only after the owner is satisfied with the local system. Access to futures from Sri Lanka is the owner's call.
