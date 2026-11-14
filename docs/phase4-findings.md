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

## Replay on real history (local, no external calls)

`uv run getrich replay [--write]` replays 2,509 days of stored BTC and ETH daily bars through the real gate, cost model and approved limits, with the Phase 3 pre-registered primary rule fixed in advance (nothing tuned on this). Full report: [phase4-replay.md](phase4-replay.md).

- **The system behaves.** Zero invariant violations over 347 trades (334 at 2x costs): risk per trade never above 0.5% of equity, exposure at entry never above 20%, whole exchange steps and minimum sizes respected, cash never negative, nothing opened under a halt. The gate refused only 21 signal days (15 for stops that were too tight, 5 for minimum size, 1 for exposure room). Seven replay tests include a true gap through a stop (it fills at the gapped open and loses more than its risk budget, as it should).
- **The rule is not good.** Sharpe 0.39 against 0.99 for the research baseline (vol-scaled trend) and 0.87 for buy and hold, 41% winners, median trade -1.03 R, average +0.10 R. Fees took about a third of gross profit. At the approved minimal limits the account earns about +2.3% a year (+15.9% in total over six and a half years) with a 15% drawdown. The stop-and-target structure appears to hurt a trend rule: 188 of 347 trades ended at the stop.
- **It has been losing for 32 months.** Equity peaked at $682 on 2024-03-11 and ended at $580 on 2026-11-13, which is 14.96% below the peak: 0.04 points short of the 15% drawdown halt. At 2x costs the halt tripped on 2026-10-24. Run live today, the system would be at the edge of halting itself.
- **Design note, not a bug:** the exposure cap binds when a position is opened and nothing trims a winner afterwards, so marked exposure peaked at 21.4%. If you want the 20% to be a hard ceiling, the gate needs a trim or rebalance rule. Say so and I will add one.
- **What it can and cannot say.** Same history the research already looked at, so it cannot confirm an edge, and a pass means only that the plumbing is sound. The trained Phase 2 models are not part of this replay: they were fitted inside cross-validation and no final model was ever saved, so there is nothing to load. They also did not beat this rule, so they are not what I would wire in next.

## Verified, and not

Verified: 69 new tests, none touching a network (gate rules including "never loosens", limits tamper handling, the lifecycle, stops, gaps, kill switch, latch, approval re-check, signing checked against an independent HMAC computation, protective-stop failure, lookup after a server error, clock resync, a fake exchange end to end). Also run for real on your data: a paper proposal was sized and reviewed, then rejected.

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
