# Replay of the order path on stored history

2020-01-01 to 2026-11-14 (2510 days; trading starts 2020-05-07 when the slowest trend pair has data). BTCUSDT and ETHUSDT daily bars, start equity $500. Every entry went through the real risk gate with the approved `minimal` limits (exposure cap 20%, drawdown halt 15%, daily loss halt 2.5%) and the project cost model (10 bps fee and 5 bps slippage per side; 2x shown too).

Rule, fixed before running (the Phase 3 pre-registered primary rule, nothing tuned here): enter at 2/3 or more trend votes when flat; stop 2 sigma below, take profit 4 sigma above, sell at the close after 20 days; one position per symbol.

## Did the system behave?

- **base costs:** 0 invariant violations over 348 trades (at entry: risk per trade at most 0.5% of equity, exposure at most 20%, whole exchange steps, minimum size, cash never negative, nothing opened under a halt). Drawdown halt tripped on 2026-11-14.
- **2x costs:** 0 invariant violations over 334 trades (at entry: risk per trade at most 0.5% of equity, exposure at most 20%, whole exchange steps, minimum size, cash never negative, nothing opened under a halt). Drawdown halt tripped on 2026-10-24.
- The exposure cap binds when a position is opened and positions are not trimmed afterwards, so a winner drifts above it: the marked exposure peaked at 21.4% of equity. The worst single trade lost -1.16 R (a gap through a stop loses more than the risk budget).
- Base-cost equity: worst drawdown -15.4% from the peak on 2024-03-11 ($682) to the trough on 2026-11-14 ($577); at the end of the data equity is $577, -15.4% below its peak.
- Signal days with a flat symbol: 370; entries taken 348; gate refusals by first failing check: stop_distance 15, quantity 5, exposure_room 1, halt_latch 1.

## Results

| | Total return | CAGR | Sharpe | Max drawdown | Worst day | vs. buy and hold Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| gated trend rule, base costs | +15.3% | +2.2% | 0.38 | 15.4% | -2.0% | -0.48 |
| buy and hold, base costs | +830.4% | +40.7% | 0.86 | 76.3% | -21.1% | |
| vol-scaled trend (research baseline), base costs | +129.0% | +13.5% | 0.98 | 18.7% | -5.4% | |
| gated trend rule, 2x costs | +11.1% | +1.6% | 0.29 | 15.0% | -2.1% | -0.57 |
| buy and hold, 2x costs | +830.4% | +40.7% | 0.86 | 76.3% | -21.1% | |
| vol-scaled trend (research baseline), 2x costs | +125.1% | +13.2% | 0.96 | 19.0% | -5.4% | |

Sharpe does not depend on how much is invested, so it compares the gated rule with the full-size baselines fairly. Total return and drawdown do not: the approved limits cap the gated rule at 0.5% of equity at risk per trade and 20% invested, so its return is small by design.

## Trades (base costs)

- 348 trades, 41% winners, average +0.10 R, median -1.03 R, profit factor 1.13.
- Exits: stop 189, take_profit 114, timeout 45. Average hold 8.4 days. Fees paid $34.52 against net profit $+76.57.
- Average exposure 9.8% of equity; in the market 67% of days.

| Year | Trades | Net P&L | Avg R | Gated return | Buy and hold return |
|---|---:|---:|---:|---:|---:|
| 2020 | 51 | +71.44 | +0.60 | +13.2% | +391.5% |
| 2021 | 75 | +34.32 | +0.16 | +6.8% | +199.4% |
| 2022 | 4 | -12.54 | -1.04 | -1.9% | -65.1% |
| 2023 | 60 | +25.83 | +0.09 | +5.5% | +122.7% |
| 2024 | 73 | +22.03 | +0.11 | +2.6% | +83.3% |
| 2025 | 63 | -32.47 | -0.10 | -5.2% | -6.2% |
| 2026 | 22 | -32.02 | -0.53 | -5.3% | -33.5% |

| Symbol | Trades | Net P&L | Avg R |
|---|---:|---:|---:|
| BTCUSDT | 176 | +55.54 | +0.11 |
| ETHUSDT | 172 | +21.03 | +0.09 |

## How to read this

- This is one rule on one history that the research already looked at, so it cannot confirm an edge. Phase 1 and Phase 3 put the same rule's Deflated Sharpe below the 0.90 bar.
- A pass here means the plumbing behaves on real data (limits respected, costs paid, halts honoured). It does not mean the rule is profitable going forward.
- Results at 2x costs show how fragile the rule is to costs, which are assumptions until measured with micro-live trading.
