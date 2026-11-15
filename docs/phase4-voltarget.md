# Volatility-scaled trend through the gate

2020-05-07 to 2026-11-14, BTCUSDT and ETHUSDT daily bars, start equity $500, limits: moderate (exposure 50%, drawdown halt 30%, daily halt 5.5%, risk per trade 2.0%). Every buy and sell went through the real gate.

Rule (fixed in advance, see `trading/replay_voltarget.py`): target weight = 0.5 x trend signal x min(1, 20% / EWMA vol) per coin; buy through the gate when flat, sell down when the target falls 10 points below the current weight, exit at zero; a protective stop 3 sigma below the fill, set once. The gate allows one position per symbol and no adding, so a position keeps the size it was bought at.

## Did the system behave?

- Invariant violations: base 0, 2x 0. Drawdown halt: base never tripped, 2x never tripped.
- Events (base): {'entry': 31, 'stop': 15, 'exit': 15, 'trim': 3}. Gate refusals by first failing check: {'stop_distance': 4}. What bounded each entry's size: {'requested quantity': 31}.
- Average requested position 5.3% of equity; average marked exposure 13.1%. The limits did not bind: the volatility target already keeps positions far below the cap.

## Results

| | Total return | CAGR | Sharpe | Max drawdown | Worst day |
|---|---:|---:|---:|---:|---:|
| vol-scaled trend through the gate, base costs | +67.0% | +8.2% | 0.82 | 13.3% | -4.7% |
| vol-scaled trend through the gate, 2x costs | +66.3% | +8.1% | 0.81 | 13.5% | -4.7% |
| gated trend rule (stop 2 sigma, take profit 4 sigma), base costs | +73.0% | +8.8% | 0.52 | 30.1% | -6.3% |
| gated trend rule, 2x costs | +49.1% | +6.3% | 0.41 | 31.6% | -6.4% |
| vol-scaled trend, research baseline (free rebalancing, no gate), base costs | +129.0% | +13.5% | 0.98 | 18.7% | -5.4% |
| buy and hold, equal weight BTC and ETH | +830.4% | +40.7% | 0.86 | 76.3% | -21.1% |

## Reading it

- The gate-compatible version earns less than the research baseline because it cannot add: a position opened at one or two trend votes stays small even when the trend strengthens, and the 3 sigma stops (15 of them) probably end positions the baseline would have kept.
- Its risk is small and steady. Compared with the gated trend rule under the same limits it has a lower drawdown for a comparable or better Sharpe, which is the point of volatility scaling.
- Everything here is in-sample on one crypto cycle, with one pre-declared stop multiple. It is not a test of an edge, and buy and hold still returned far more.
