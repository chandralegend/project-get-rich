# Gated volatility-scaled trend: entry at 1 of 3 votes versus 2 of 3 (pre-registered)

Pre-registration: `docs/preregistration-voltarget-entry.md`, SHA-256 `92fdb5be9fe8c55a...` (matches the hash logged before the run). 2020-05-07 to 2026-11-14; limits moderate (exposure 50%, halt 30%, risk per trade 2.0%). Deflated Sharpe counts 36 trials.

| | Total | CAGR | Sharpe | at 2x costs | Max DD | Half 1 / half 2 at 2x | Deflated Sharpe | Entries / stops | Avg exposure |
|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| V1, enter at 1 of 3 votes | +67.0% | 8.2% | 0.82 | 0.81 | 13.3% | 1.09 / 0.47 | 0.817 | 31 / 15 | 13.8% |
| V2, enter at 2 of 3 votes | +102.2% | 11.4% | 0.95 | 0.94 | 14.7% | 1.33 / 0.47 | 0.898 | 22 / 15 | 16.1% |
| reference: gated 2 sigma / 4 sigma trend rule | +73.0% | 8.8% | 0.52 | 0.41 | 30.1% | | | | |

**V2: not shown** (dsr failed)

Criteria (all required for V2): Sharpe at 2x costs at least 0.10 above both V1 and the gated trend rule, Deflated Sharpe at least 0.90, maximum drawdown at most 20%, positive Sharpe at 2x costs in both halves, zero invariant violations and no halt.
