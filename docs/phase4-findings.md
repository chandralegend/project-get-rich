# Phase 4: risk gate, paper broker, approval flow, Binance testnet adapter

Date: 2026-11-14. Status: the core is built and tested and runs on paper. The Binance Spot Testnet adapter is built and tested against a fake exchange but has never talked to the real testnet, because it needs keys only you can create. **Nothing here can place a real order**: there is no live venue, and the testnet adapter is locked to the testnet host.

## What exists

| Piece | Where | What it does |
|---|---|---|
| Hash-pinned limits | `trading/limits.py` | The gate trusts `config/limits.toml` only while it matches the hash you pinned. `limits-approve` pins what it writes; `getrich limits-pin` re-pins. Edit the file by hand and every new entry fails closed, with the reason. Exits are never blocked. I pinned the profile you approved earlier (minimal, unchanged since). |
| Risk gate | `trading/gate.py` | A pure function: no database, network, clock or randomness. It can only tighten a request. Entry checks, in order: kill switch, limits pinned, drawdown latch and 15% halt, 2.5% daily loss halt, one position per symbol, fresh price (3 hours for hourly bars), stop required and 0.5% to 20% below price, cost gate (round-trip cost at most 0.25R), optional claimed-edge check (3x costs), cancel-to-fill conduct guard, then sizing as the smallest of the 0.5% risk budget, the 20% exposure cap, cash, and any requested size, floored to the exchange step, with a minimum-size rule that rejects rather than overshoot the risk budget. Sells can only reduce a position and are always allowed, even halted or killed. |
| Order lifecycle | `trading/service.py` | `propose` runs the gate and stores the proposal (nothing is sent). `approve` re-runs the gate on fresh state; the size can only shrink. Proposals expire after 15 minutes. A venue failure leaves a `failed` order and no fills. Every step is logged under one `decision_id`. |
| Paper broker | `trading/sim.py` | Fills pay the project cost model (10 bps fee and 5 bps slippage per side). A touched stop fills at the stop, or at the open if the bar gapped through it. If one bar touches both stop and take profit, the stop is assumed first. Bars before the entry never trigger a stop. |
| Kill switch and halts | `trading/service.py` | `kill` writes the block first, then flattens, so a failure while flattening still leaves entries blocked. The 15% drawdown halt is a latch file that survives a recovery in equity; only `unhalt` clears it. |
| Terminal flow | `cli.py` | `propose`, `approve` (asks you to type yes and refuses without an interactive terminal), `reject`, `orders`, `positions`, `paper-tick`, `kill`, `unkill`, `unhalt`, `limits-pin`. The agents never approve. |
| Binance testnet adapter | `trading/binance_testnet.py` | HMAC-signed requests with the key in `X-MBX-APIKEY`; exchange filters read from `exchangeInfo`; market buy, then an exchange-side market stop (`STOP_LOSS`) or, with a take profit, the current OCO endpoint (`/api/v3/orderList/oco`, not the deprecated one). Orders carry a client order id and are never resent blindly: an ambiguous failure is resolved by lookup. If the stop cannot be placed after a buy, the position is sold at market straight away; if that also fails the error says the position is unprotected. A buy fee paid in the base asset is folded into the fill price so the book matches what is actually held. |
| Alerts | `ops/watchdog.py` | P1 while the drawdown halt is latched or the kill switch is on (they clear the moment you clear them). P0 for an unprotected position or a missing stop (from the last 24 hours of events). P1 if a paper position is open while hourly bars are stale, since its stop is then not being checked. |
| Jobs | `ops/launchd` | `paper-tick` hourly (checks stops, latches the drawdown halt, snapshots equity). `collect-binance` now fetches hourly bars as well as daily ones. |

## Found while building

- **The order path needs hourly bars, and the collector job only fetched daily ones.** The hourly history was a one-off backfill, so the gate (correctly) rejected every entry as "stale price" 3 hours later. The job now collects `1d` and `1h`.
- **Testnet prices differ from mainnet.** For the testnet venue the gate uses the testnet's own last price and its own exchange filters, not stored mainnet bars.
- **At $500 the sizes are tiny but valid.** A 5% stop on BTC sizes to about 0.0012 BTC (about $80) risking $2.50. Gold-style min-size problems do not arise for crypto spot at this size.

## Verified, and not

Verified: 62 new tests, none touching a network (gate rules including "never loosens", limits tamper handling, the lifecycle, stops, gaps, kill switch, latch, approval re-check, signing checked against an independent HMAC computation, protective-stop failure, lookup after a server error, clock resync, a fake exchange end to end). Also run for real on your data: a paper proposal was sized and reviewed, then rejected.

Not verified against the real testnet: everything the fake exchange assumes about response shapes (I used the fields in Binance's docs, read by a helper; the `RESULT` response and `/order/test` pages were not retrieved), and whether the exchange accepts a `STOP_LOSS` sell at the prices the gate allows. The first real run will tell.

## Not done

- **Reconciliation.** The architecture's Phase 4 exit asks that reconciliation matches the exchange. There is no comparison of the book against the testnet account yet.
- **Fault injection** against the order path (the architecture asks that every injected fault shows up in the log and raises the right alert).
- **Exchange-side cancels are not counted** by the cancel-to-fill guard (the adapter cancels its own protective order on an exit, which is normal). The guard counts only orders marked cancelled in the book, which today is none. It matters only once non-protective resting orders exist.
- **No signal source.** Proposals are manual. Nothing proposes trades from the trend rule or any model, and nothing should until there is evidence of an edge. Phase 2 and the meta-label experiment found none.
- **Binance live trading, cTrader, MT5.** Not started. Live Binance would use Ed25519 keys held outside the project folder, a separate process, and your explicit go-ahead.

## To run the testnet

1. Create free testnet keys at `testnet.binance.vision` (log in with GitHub). They are virtual money and the testnet is wiped about monthly.
2. Put `GETRICH_BINANCE_TESTNET_KEY` and `GETRICH_BINANCE_TESTNET_SECRET` in `.env`. I will not read or enter them.
3. `uv run getrich propose buy BTCUSDT --stop <price> --venue testnet`, review the verdict, then `uv run getrich approve <id> --venue testnet`. The virtual account is sized as if equity were `GETRICH_PAPER_EQUITY` (default 500), not the testnet's large balance.
