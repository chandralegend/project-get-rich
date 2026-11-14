# Track 5: Risk, Position Sizing and Portfolio / Asset Management

Date of research: 2026-11-14. Scope: stocks, forex, metals (gold/silver), CFD/spot and futures, small retail account, LOCAL-FIRST (only Anthropic Claude as a cloud LLM; everything else local, Apple Silicon Mac assumed).

This is engineering research, not personalized financial advice. Every number in the "Suggested defaults" tables is a **starting point to be validated** by backtest, paper trading and stress tests; none is a recommendation.

Evidence labels used throughout:
- **[seen]** = I read it in a fetched page or search result this session (URL given).
- **[bg]** = standard background knowledge, NOT fetched this session. Treat as unverified until checked.
- **[unverified]** = a source made the claim but it is thinly sourced, conflicting, or I could not corroborate it.

---

## 0. TL;DR

1. **The risk engine must be a deterministic, local, separate process that owns the broker credentials and is the only path to the market.** LLM agents, forecasters and the profitability classifier produce *order intents / views*; the risk gate approves, shrinks or rejects them. It can never be loosened by an agent, and it runs with the internet and the Claude API down. See Section 2 and Section 11 (Local-first stack).
2. **Sizing: use fixed-fractional risk-to-stop as the base (0.25-0.5% equity per trade to start), scaled by volatility, capped by hard portfolio limits.** Treat Kelly as an *upper bound on what is sane*, not a target. If your edge estimate is 2x too high, full Kelly yields roughly zero growth ([bg] derivation, Section 1.3); fractional Kelly (quarter to half) is the commonly cited hedge ([seen] secondary sources, Section 1.3).
3. **Classifier probability to bet size**: López de Prado's AFML ch. 10 recipe (z = (p - 1/k)/sqrt(p(1-p)); size = 2*Phi(z) - 1) is simple, but it is only as good as the calibration of p. Calibrate first (isotonic/Platt on out-of-sample folds), then discretize, then cap, then cost-gate ([seen] via secondary MQL5 write-up; verify against book Snippet 10.1).
4. **Portfolio construction for 5-30 instruments: do not use raw mean-variance.** Default to risk-based methods (inverse-vol / risk parity / HRP) on a shrunk covariance (Ledoit-Wolf/OAS). Use **Black-Litterman as the integration point for LLM "views"**, with view confidence (Omega) set from *measured* historical hit-rate, never from the LLM's self-reported confidence, and views expiring on a TTL.
5. **The biggest hidden risk in a multi-asset FX + gold + equities book is USD concentration** (long EURUSD, long XAUUSD, short USDJPY, long US equities are largely one bet). Decompose every position into currency/factor legs and cap *net factor exposure*, not just per-symbol size. Gold's classic inverse link to real yields has been unreliable since 2022 ([seen] Kitco/Janus Henderson), so do not hard-code that relationship as a hedge.
6. **Gaps beat stops.** SNB Jan 2015 (CHF up ~30% in minutes, retail brokers insolvent or bailed out), Jan 2026 silver/gold crash with repeated CME margin hikes ([seen], details unverified), March 2020 cross-asset liquidation including gold ([seen]). Design for slippage through the stop, margin changes, and correlation-to-1 in stress.
7. **PDT status (verified): the US $25k pattern-day-trader minimum is eliminated.** SEC approved FINRA's Rule 4210 amendments on 2026-04-14; effective 2026-06-04; brokers may phase in until 2027-10-20; replaced by an intraday margin standard. Check your specific broker's implementation. ([seen] FINRA Reg Notice 26-10.)
8. **Reddit, X, Instagram were not reachable** from this toolset (details in Section 9). Community evidence below is from forums, blogs, Hacker News tooling and regulator/press documents instead.

---

## 1. Position sizing methods

### 1.1 Comparison table

| Method | Formula / idea | Strengths | Weaknesses | Use here as |
|---|---|---|---|---|
| Fixed-fractional (risk-to-stop) | units = (equity * r) / (stop distance * point value) | Simple, survival-oriented; widely recommended (1% rule; 0.25-0.5% for many profitable traders per [seen] [CrossTrade](https://crosstrade.io/learn/risk-management/one-percent-rule), [Hackernoon](https://hackernoon.com/why-bet-size-kills-more-trading-accounts-than-bad-signals)) | Needs a real stop; breaks under gaps; ignores correlation between positions | **Base layer** |
| ATR-based sizing | stop = k * ATR(n); units from fixed-fractional | Adapts stop and size to current volatility; one formula across FX/gold/equities | ATR lags regime shifts; k is a tunable (overfit risk) | Stop-distance generator feeding fixed-fractional |
| Volatility targeting | w_i = (sigma_target / sigma_hat_i) * signal_i, capped | Equalizes risk contribution across assets; automatically de-risks in high vol | Evidence for *alpha* from vol-managing is contested: Moreira-Muir claim big Sharpe gains; Cederburg et al. and Barroso-Detzel find gains vanish out-of-sample or after costs; DeMiguel et al. (J. Finance 2024) push back ([seen] search summary; see [LBS DeMiguel et al.](https://lbsresearch.london.edu/id/eprint/3716)) | Use as a **risk control** (stabilize risk), do not count on it as alpha |
| Kelly (full) | Binary: f* = p/l - q/g. Continuous: f* = (mu - r)/sigma^2 ([seen] [Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion)) | Growth-optimal if inputs are exact | Valid "only for fully known outcome probabilities" ([seen] same); huge drawdowns; overbet when edge is overestimated | **Never full.** Sanity ceiling |
| Fractional Kelly | f = c * f*, c in [0.25, 0.5] typical | Less variance/drawdown, tolerant of estimation error ([seen] [questdb](https://questdb.com/glossary/kelly-criterion-for-optimal-betting), [arXiv 2010.12508](https://arxiv.org/pdf/2010.12508)) | Still needs mu and sigma; mu is the noisy input | Ceiling on fixed-fractional, only when a calibrated edge estimate exists |
| Risk parity / equal risk contribution | w_i proportional such that w_i*(Sigma w)_i equal | No return forecasts needed | Leverage needed to hit return targets (margin!); relies on covariance estimate | Portfolio-level allocator across strategies/assets |
| Probability to bet size (AFML ch.10) | z = (p - 1/k)/sqrt(p(1-p)); m = 2*Phi(z) - 1; signed by side ([seen] secondary [MQL5 article](https://www.mql5.com/en/articles/21824); verify vs book) | Directly maps classifier output to size; naturally handles meta-labeling | Overconfident probabilities flow straight into size ([seen] [MQL5 part 12](https://www.mql5.com/en/articles/21938)); step discretization needed to avoid churn | Size multiplier m in [0,1] on top of base risk |
| Cost/slippage-aware sizing | Trade only if expected edge (net) > k * round-trip cost; no-trade band around target | Prevents cost bleed, especially on small accounts and on gold/FX CFDs with swaps | Requires a reliable cost model (spread by time of day, swap, commission) | **Gate** after sizing |

### 1.2 Recommended composition (pipeline order)

```
signal side + p (calibrated) 
  -> base_risk = equity * r0                         (r0 start: 0.25-0.5%)
  -> stop distance = k * ATR  (or structure stop)    (k start: 2-3 ATR)
  -> units_raw = base_risk / (stop_dist * pip_value)
  -> * m(p)                                          (AFML map, discretized in 0.1-0.25 steps, m <= 1)
  -> * vol_scale = min(1, sigma_target / sigma_hat)  (never scale UP above 1 early on)
  -> cost gate: skip if edge_net < k_c * (spread + 2*slippage + swap*hold)
  -> min-lot check: if min tradable lot's risk > 1.5 * base_risk -> SKIP (do not round up)
  -> portfolio gate (Section 3): factor caps, heat, margin
  -> final units (round DOWN to lot step)
```

All steps are deterministic functions; they live in the risk engine, not in the agent.

### 1.3 Kelly and estimation error (the practical part)

- For the continuous case, f* = (mu - r)/sigma^2. [seen] [Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion) gives a worked example: 6% excess return and 15% vol -> f* about 267%, and notes Thorp and Rotando estimated about 117% for the S&P 500. It also states the formula requires known probabilities and calls out garbage-in/garbage-out.
- [bg, standard derivation, not fetched] With fraction c of Kelly, long-run growth is approximately r + (mu - r)^2/(2 sigma^2) * (2c - c^2). At c = 1 you get the maximum; at c = 2 growth equals the risk-free rate (zero excess growth); above that it's negative. So **if your estimated edge is 2x the true edge and you bet "full Kelly" on the estimate, you are at c = 2 in reality**. This is the core argument for half/quarter Kelly under estimation error. Reproduce this numerically in the project's unit tests before relying on it.
- [seen] Secondary sources: typical operating range is a quarter to a half of computed Kelly; where edge is unknown, a conservative fixed fraction can outperform a Kelly number built on inaccurate inputs ([questdb](https://questdb.com/glossary/kelly-criterion-for-optimal-betting), [Polymarket-bot docs](https://mintlify.com/joicodev/polymarket-bot/risk/kelly-criterion), [arXiv 2010.12508](https://arxiv.org/pdf/2010.12508)).
- Engineering rule: estimate edge with **shrinkage toward zero** (e.g., posterior mean of edge with a skeptical prior), use a *lower confidence bound* of mu rather than the point estimate, then apply c <= 0.25 at the start. Kelly then only ever *reduces* size relative to fixed-fractional.

### 1.4 Retail reality: min lot sizes, commissions (small accounts)

- Quantization is the small-account killer: at 0.5% risk on a $2,000 account the risk budget is $10; if the smallest lot's stop-risk is $25, the "right" size does not exist. Rule: **skip, do not round up** (above). Contract sizes and lot steps are broker-specific; read the symbol specification from the broker API at startup. One XAUUSD swap example in [seen] results implies 1 standard lot = 100 oz, with 0.01 lot sizes common, but this is from a swap-calculation page and varies by broker ([source](https://www.moomoo.com/sg/support/topic5_609) / [Pepperstone guide](https://pepperstone.com/en-eu/learn-to-trade/trading-guides/what-are-swaps-how-to-calculate-swaps)) [unverified].
- US PDT status (verified, [seen]): see Section 8.
- ESMA/FCA-style retail CFD accounts: leverage caps and 50% close-out (Section 3.4).

---

## 2. Design principle: risk is deterministic, local, and authoritative

**Principle:** *No LLM, forecaster, or classifier can place an order, move a stop, or change a limit except through a deterministic risk gate that (a) runs locally, (b) has no dependency on network or LLM availability, and (c) can only be loosened by a human via an out-of-band path.*

### 2.1 Architecture

```
 [Claude agents]  [forecasters]  [classifier]  [strategies]
        \              |             |            /
         +-------------+-------------+-----------+
                       |   OrderIntent / View (typed schema, no broker access)
                       v
              +---------------------+      localhost IPC (unix socket / gRPC)
              |   RISK GATE (own    |<---- reads limits.toml (read-only, hash-pinned)
              |   OS process, own   |<---- reads state.sqlite (positions, equity, PnL, heat)
              |   user account)     |
              +----------+----------+
                         | approved / resized / rejected (with reason code)
                         v
              +---------------------+
              |  Execution adapter  |  <- only holder of broker API keys
              +----------+----------+
                         v
                      BROKER  (server-side protective stops/OCO live HERE)
```

### 2.2 Rules that keep the risk engine authoritative

1. **Credential isolation.** Only the execution adapter (behind the risk gate) holds broker keys. Agents run under a different OS user / sandbox with no keys and no network route to the broker. Prompt-level instructions ("never exceed 10% position") are **not** controls; for contrast, Lumibot's AI example puts its 10%-cap/no-leverage guardrails *in the prompt* and uses a read-only reviewer with `allow_trading=False` ([seen] [Lumibot README](https://github.com/Lumiwealth/lumibot)); copy the read-only-agent idea, not the prompt-as-control idea.
2. **Asymmetric authority ("tighten-only").** Agent-facing API can only: propose entries (subject to gate), request reduce/flatten, add a blackout, lower a risk multiplier. It cannot: remove a blackout, raise limits, disable the gate, change the config path. NautilusTrader's design is a useful reference: `TradingState` ACTIVE -> REDUCING -> HALTED with progressively fewer permitted commands, and cancel/query commands bypass the risk engine ([seen] [Nautilus execution docs](https://nautilustrader.io/docs/latest/concepts/execution/)). Note it also has a `bypass` option that skips checks including trading-state enforcement; **in our build, no bypass flag may exist in production code.**
3. **Config immutability.** limits file read-only, content hash pinned in a second location; the gate refuses to start (or goes HALTED) on mismatch. Loosening requires a human CLI action with a cool-off delay (e.g., effective next session).
4. **Fail-safe defaults.** Gate goes to REDUCING (reduce-only) automatically on: stale market data (> N seconds), broker disconnect, clock skew, state-DB mismatch vs broker positions at reconciliation, heartbeat loss from any component, unknown instrument, or LLM-originated intent that fails schema validation.
5. **Broker-side last line of defence.** Local machine can crash/sleep. Every position carries a **server-side** protective stop (or OCO) at the broker, so the account is protected if the whole local stack dies. (Caveat: stops can gap, see Section 7.) Add a periodic "dead-man" flag where the adapter refreshes a keepalive; if it stops, a broker-side or scheduled mechanism flattens, where the broker supports it [bg; check per broker].
6. **No network dependency inside the gate.** Limits, calendars (cached daily), volatility estimates, correlation matrices, FX conversion rates all come from local cache with TTLs; stale cache => conservative fallback (e.g., block entries near typical event times if the news calendar cache is stale).
7. **Claude API down is a normal state.** Views from Claude carry a TTL; as a view ages, its Black-Litterman Omega inflates and the portfolio decays toward the prior. No Claude => the book drifts to the neutral risk-based portfolio, never to "stuck leveraged".
8. **Injection hardening.** News/web text read by Claude is untrusted; Claude's output is parsed into a bounded schema (direction, magnitude capped, confidence capped, TTL capped). Out-of-bounds fields are clipped or rejected, never executed. A manipulated news item can at worst nudge a view inside the bounds.
9. **Audit.** Every approve/resize/reject writes an append-only record (intent, limits evaluated, reason code). The same codepath runs in backtest, paper and live so the backtest exercises the real gate. (Nautilus' RiskEngine runs in backtest, sandbox and live [seen]; replicate that parity.)

---

## 3. Layered risk-control specification

All values are **starting points to be validated** (by stress tests, backtests, and paper trading). Where a value comes from a source it is cited; the rest are engineering judgment [bg].

### 3.1 Layer A: Pre-trade (per order, in the gate)

| Check | Default (starting point) | Notes |
|---|---|---|
| Max risk per trade (to stop) | 0.25-0.5% of equity | Sources commonly cite 1% as ceiling; 0.25-0.5% for many profitable traders ([seen] [CrossTrade](https://crosstrade.io/learn/risk-management/one-percent-rule), [curvedtrading](https://curvedtrading.com/articles/en/how/risk-management-beginners/) via search) |
| Stop required | Reject any intent without stop or defined max-loss | Server-side stop attached at submission |
| Max notional per order | e.g., 2-3x equity per order for FX, lower for metals | Nautilus has `max_notional_per_order` [seen] |
| Max position per instrument | e.g., 5% equity at risk, 25% equity notional (stocks); by asset class for FX/metals | |
| Order rate limit | e.g., max N orders/min, M/day | Nautilus enforces submit/modify rate limits [seen]. Protects against runaway loops (Knight-style) |
| Fat-finger / price sanity | Reject price > X% from last/mid or > Y ATR | |
| Spread / liquidity gate | Reject if spread > k * typical spread (e.g., 3x) or volume/liquidity below threshold | Critical around rollover (~21:00 UTC) and thin sessions |
| Cost gate | edge_net > k_c * costs; skip if min-lot risk > 1.5x budget | Section 1.2 |
| News blackout | No new entries from -T1 to +T2 around tier-1 events (NFP, FOMC, CPI, central bank decisions); T1/T2 start 15-30 min | Calendar is local cache; stale cache => conservative |
| Weekend/gap rule | Reduce or flatten before Friday close for positions without sufficient stop buffer; no new entries last 1-2 h before close | See Section 7 |
| Duplicate/idempotency | Same intent id rejected twice | |
| Market state | Reject if market closed, halted, or data stale | |
| Schema/bounds on LLM-originated intents | Clip or reject | Section 2.2 #8 |

### 3.2 Layer B: Intra-trade (per position)

| Control | Default | Notes |
|---|---|---|
| Initial stop | k * ATR (k 2-3) or structural; server-side | |
| Trailing / break-even | Optional; trail by k_t * ATR after +1.5R | Lean ships `TrailingStopRiskManagementModel` default 5% off peak unrealized profit [seen](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/supported-models) |
| Time stop | Close if not working after N bars/days | Prevents swap bleed on carry-negative CFD positions |
| Max adverse excursion check | If MAE exceeds backtest's 95th pct, flatten and flag | Early detection of broken thesis |
| No averaging down | Reject adds to losing positions unless pre-planned | Common blow-up pattern (Section 9) |
| Never widen stops | Gate rejects stop modifications that increase risk | "Moving a stop further away ... worse than not having one" ([seen] [work-club summary](https://work-club.com/trading-mistakes-risk-management/amp/)) |
| Take-profit / scale-out | Optional | |

### 3.3 Layer C: Portfolio

| Control | Default | Notes |
|---|---|---|
| Portfolio heat (sum of open risk-to-stop) | <= 3-5% of equity | [bg] common practice; validate |
| Net USD exposure | Cap |net USD delta| at e.g. 1.5-2x single-trade risk budget equivalents; hard cap % of equity notional | Decompose every position into currency legs: long EURUSD = long EUR / short USD; long XAUUSD = long gold / short USD; short USDJPY = short USD / long JPY; US equities = separate USD-asset factor |
| Factor buckets | USD, equity beta (risk-on), rates/real-yield, safe-haven (gold/JPY/CHF) | Cap net exposure per bucket |
| Asset-class caps | e.g., FX <= 50%, metals <= 25%, equities <= 50% of risk budget | |
| Correlation cluster limit | Positions in a cluster (|rho| > 0.6 on shrunk covariance) share one risk allowance, e.g., 1.5x single-trade risk | Use stress correlation: assume rho -> 1 inside clusters in stress (March 2020 evidence below) |
| Gross / net leverage | Effective leverage cap e.g. <= 3-5x equity (well below broker max) | Broker max for retail CFDs: 30:1 majors, 20:1 gold per ESMA ([seen] [ESMA](https://www.esma.europa.eu/press-news/esma-news/esma-agrees-prohibit-binary-options-and-restrict-cfds-protect-retail-investors)) |
| Margin utilization | Used margin <= 20-30% of equity; free margin buffer >= 2x worst-case stress loss | CME margin hikes can change requirements overnight (Section 7) |
| Portfolio VaR/ES budget | e.g., 1-day 99% ES <= 3% equity (historical + stressed) | Computed locally (Section 6) |
| Concentration | No single instrument > X% of portfolio risk | |
| Liquidity | Position size < k% of avg daily volume (stocks); spread-widening stress for FX/gold | |

### 3.4 Layer D: Account-level circuit breakers

| Control | Default | Source / reasoning |
|---|---|---|
| Daily loss limit (equity-based, includes floating P/L) | 2% soft (stop new entries, reduce-only), 3% hard (flatten) | Prop-firm reference: FTMO daily limits 3-5% measured against equity incl. floating P/L ([seen] [FTMO](https://ftmo.com/en/trading-objectives/)); keep internal limits at ~50-60% of any external limit |
| Drawdown ladder (from equity high-water mark) | -5%: halve risk; -10%: flat, human review; -15/-20%: strategy retired pending post-mortem | Compatible with [seen] blog ladders: trim at 5%, halve at 10%, pause at 20% ([Hackernoon](https://hackernoon.com/why-bet-size-kills-more-trading-accounts-than-bad-signals)); suggestions on blogs vary widely so none is a standard |
| Consecutive loss / cooldown | After N stop-outs in window, lock for D hours | Freqtrade `StoplossGuard` and `CooldownPeriod` ([seen] [Freqtrade plugins](https://www.freqtrade.io/en/stable/plugins/)) |
| Per-strategy drawdown stop | Kill strategy if live DD > ~1.5x backtest 95th-percentile max DD | Live-vs-backtest drift (Section 6) |
| Margin-level floor | If margin level < e.g. 200% (broker close-out is 50% under ESMA [seen]), auto-reduce | You want to act long before the broker does |
| Max trades/day | Cap | Prevents runaway loops |
| Withdrawal/rebalance rules | Recompute risk from *current* equity (risk shrinks after losses) | "fixed-dollar risk grows as a percentage when the account falls" ([seen] guide summary) |

### 3.5 Layer E: System-level kill switches

| Trigger | Action |
|---|---|
| Manual hotkey/CLI `halt` | State HALTED: cancel working orders; optional flatten |
| Heartbeat loss (strategy, data feed, risk engine, adapter) | REDUCING + alert; after T seconds flatten (configurable) |
| Position reconciliation mismatch (local vs broker) | HALTED until a human resolves |
| Data feed stale or crossed/implausible quotes | No new orders |
| Order-rate or reject-rate spike | HALTED (Knight-style runaway protection; [seen] SEC found no pre-submission check or threshold-based blocking: [SEC press release 2013-222](https://www.sec.gov/news/press-release/2013-222), [WilmerHale](https://www.wilmerhale.com/en/insights/client-alerts/knight-capital-settles-rule-15c3-5-violations-with-sec-agrees-to-pay-12-million)) |
| Slippage anomaly (realized slippage > k * model for N fills) | REDUCING |
| Config hash mismatch / unsigned change | HALTED |
| Unexpected exit of the risk engine | Execution adapter refuses all orders without a live gate lease |
| Broker-side protective stops | Always on (Layer 2.2 #5) |

Operational lesson from Knight: automated alert emails flagged the error before the open and nobody acted ([seen] same SEC summaries); a kill switch needs an *automatic* trigger, not an inbox.

---

## 4. Portfolio construction

### 4.1 Method notes

- **Mean-variance (Markowitz)** [bg]: optimizer amplifies estimation error in expected returns and in covariance (error-maximizer). With n_samples comparable to n_assets, the sample covariance has extreme eigenvalues and is ill-conditioned; shrinkage reduces the largest/smallest eigenvalue ratio and makes inversion stable ([seen] [scikit-learn covariance docs](https://scikit-learn.org/stable/modules/covariance.html)). Use MV only with constraints and shrunk inputs, or avoid.
- **Shrinkage covariance**: Ledoit-Wolf (2004) minimizes MSE of the covariance estimate; OAS (Chen et al. 2010) can do better under Gaussian data and small samples; both in scikit-learn `LedoitWolf`, `OAS` ([seen] same). Both PyPortfolioOpt and skfolio/Riskfolio expose them. For FX/metals/equity mixes, also consider EWMA vol + shrunk correlation.
- **HRP** (López de Prado 2016, J. Portfolio Management 42(4)): cluster on correlation distance, quasi-diagonalize, recursive bisection with inverse-variance allocation; does not invert the covariance; uses no return forecasts ([seen] [Wikipedia](https://en.wikipedia.org/wiki/Hierarchical_Risk_Parity)). Caveats [seen]: headline out-of-sample results are from Monte Carlo on synthetic Gaussian data; page flags conflict of interest (author-affiliated sources). Treat as a robust default, not a proven winner; compare against inverse-vol and equal-risk-contribution in your own walk-forward.
- **Black-Litterman** [bg]: posterior mean combines equilibrium prior pi = delta * Sigma * w_mkt with views (P, Q, Omega). Good fit for agent views: each LLM view is a row of P (assets/long-short pairs), Q (expected return), Omega (uncertainty). For FX/metals there is no market-cap prior; use a risk-parity or vol-scaled neutral prior. Evidence for LLM-generated views is thin: Lee et al. (arXiv [2504.14345](https://arxiv.org/abs/2504.14345)) found different LLMs have distinct "investment styles" that drive performance more than raw forecasting skill, but backtest was June 2024-Feb 2025 on stocks only ([seen]; check the PDF before citing numbers). Earlier: Kong et al. 2024 (ChatGPT-BL, BARD-BL) [seen] ([IAENG](https://iaeng.org/IJCS/issues_v51/issue_8/IJCS_51_8_04.pdf)).
- **CVaR optimization** [bg]: Rockafellar-Uryasev LP; handles fat tails/skew better than variance; needs many scenarios (sample size) and is sensitive to the tail estimate. All of Riskfolio, skfolio, PyPortfolioOpt (mean-CVaR) offer it ([seen]).
- **Risk budgeting / ERC**: specify target risk contributions per factor/asset-class bucket (e.g., FX 40/metals 20/equities 40); available in Riskfolio (risk parity with 22 convex measures) and skfolio (Risk Budgeting) ([seen]).
- **Black-Litterman view hygiene**: Omega from calibrated historical hit-rate and realized error of that view generator (per asset class, per horizon); cap |Q|; floor Omega; TTL decay; log views and outcomes for scoring.

### 4.2 Library table

Stars/last-push from GitHub REST API on 2026-11-14 where I could read them ("pushed_at" = last push to repo, not a release). Items marked n/a hit GitHub API rate-limit; stars then come from the repo page via WebFetch and last-commit is **not verified**.

| Library | Stars | License | Last push [seen] | What it gives | Local-only? | Apple Silicon note | Verdict |
|---|---|---|---|---|---|---|---|
| [Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) | 4.6k | BSD-3 | 2026-11-04 | Mean-risk (26 risk measures), risk parity (22), HRP/HERC (37), NCO, BL family (standard, Bayesian, augmented, entropy pooling), constraints, reports; built on CVXPY, optional MOSEK/Gurobi | Yes, fully local (commercial solvers optional) | Pure Python on numpy/scipy/cvxpy; cvxpy ships universal2 (ARM64) wheels [seen] ([PyPI](https://pypi.org/project/cvxpy/)); no commercial solver needed | **Primary for BL + risk budgeting + CVaR** |
| [skfolio](https://github.com/skfolio/skfolio) | 2.6k | BSD-3 | 2026-11-13 | scikit-learn-style API; HRP/HERC/NCO, BL prior, CVaR/EVaR/CDaR/MaxDD, risk budgeting, transaction costs, turnover constraints; naive baselines (equal, inverse-vol) | Yes | Same stack as above; sklearn-compatible so cross-validation (walk-forward) is natural | **Primary for model selection / cross-validated construction** |
| [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) | 6.2k | MIT | 2026-07-07 | Shrinkage covariance (LW, OAS), BL, HRP, mean-CVaR, mean-semivariance, CLA, discrete allocation to whole shares | Yes | Python + cvxpy; fine | Good for quick baselines; push is ~4 months old (stable-library behaviour or slower maintenance; I did not read issue activity) |
| [cvxportfolio](https://github.com/cvxgrp/cvxportfolio) | 1.3k | **GPL-3.0** | 2026-04-27 | Multi-period optimization with transaction/holding costs; simulator; built for "trade-off return vs risk vs cost" | Yes | Python/cvxpy; fine | Best fit for **cost-aware rebalancing**; mind GPL if you ever distribute |
| [QuantStats](https://github.com/ranaroussi/quantstats) | 7.9k | Apache-2.0 | 2026-11-02 | Tearsheets, Sharpe/Sortino/Calmar, drawdown, VaR/CVaR | Yes | Pure Python | Reporting only |
| [empyrical-reloaded](https://github.com/stefan-jansen/empyrical-reloaded) | 133 | Apache-2.0 | 2026-11-08 | Risk/perf metrics (maintained fork of Quantopian's empyrical) | Yes | Pure Python | Metrics building block |
| [pyfolio-reloaded](https://github.com/stefan-jansen/pyfolio-reloaded) | 624 | Apache-2.0 | 2026-11-02 | Tearsheets (maintained fork) | Yes | Pure Python | Reporting |
| [bt](https://github.com/pmorissette/bt) | 3.0k | MIT | 2026-11-13 | Tree-based allocation/rebalancing backtester (weighting algos incl. inverse-vol, ERC-like) | Yes | Pure Python | Good for allocation-strategy backtests |
| [ffn](https://github.com/pmorissette/ffn) | 2.7k | MIT | 2026-11-12 | Financial functions: perf stats, drawdowns, ERC weights | Yes | Pure Python | Utility |
| [vectorbt](https://github.com/polakowo/vectorbt) | 9.8k | Apache-2.0 + Commons Clause ("fair-code": cannot sell a product primarily this software) [seen] | 2026-11-11 | Fast portfolio simulation, drawdown/Sharpe/Sortino/Calmar stats, QuantStats integration | Yes | numba-based [bg: numba supports arm64; not verified here] | Great for research sweeps; limit orders/leverage/portfolio optimization listed as **PRO-only** [seen], so do not count on the OSS edition for risk sim |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | 31.5k | LGPL-3.0 | n/a (22,488 commits seen) | Real RiskEngine (Section 5) | Yes | macOS ARM64 wheels listed (developer table: macOS 15+, Py 3.12-3.14) [seen, secondary: [PyPI](https://pypi.org/project/nautilus-trader), [docs](https://nautilustrader.io/docs/latest/getting_started/installation)]; docs advise stable wheels, not dev wheels, for live | See Section 5 |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | 22.5k | Apache-2.0 | n/a (13,493 commits seen) | Risk management models (Section 5) | Local engine possible (.NET); [bg] Docker/lean-cli path; **Apple Silicon support not verified here** | Unverified | Pattern source |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | 56.9k | not stated on page (verify; [bg] GPL-3.0) | n/a | Protections (Section 5) | Yes | Python | Pattern source (crypto-focused) |
| [Lumibot](https://github.com/Lumiwealth/lumibot) | 2.2k | GPL-3.0 | n/a | Backtest + live; AI-agent examples with prompt guardrails | Yes | Python | Pattern source (and cautionary tale) |
| [cvxpy](https://pypi.org/project/cvxpy/) (dependency) | n/a | Apache-2.0 [bg] | n/a | Convex solver interface; open solvers Clarabel, SCS, OSQP, HiGHS; MOSEK/Gurobi separate | Yes | universal2 wheels for CPython 3.11-3.14 (latest seen 1.9.3) [seen]; MOSEK arm64 macOS **not verified** | Core dependency |
| [hmmlearn](https://github.com/hmmlearn/hmmlearn) (regimes) | n/a | BSD-3 [bg] | n/a | Gaussian HMM | Yes | Compiled extension; wheels for arm64 macOS **not verified**; `scikit-learn`-style fallback via `GaussianMixture` | Optional |

Notes:
- Last-commit dates for Nautilus, LEAN, Freqtrade, Lumibot, hmmlearn, cvxpy were **not verified** (GitHub API rate limit). Rerun before final selection.
- PyPortfolioOpt and others show no tagged "Releases" on their pages in the fetch output; do not infer abandonment from that.

---

## 5. Open-source frameworks: what to copy

### 5.1 NautilusTrader RiskEngine ([docs](https://nautilustrader.io/docs/latest/concepts/execution/), [seen])
Copy: pre-trade check list (price/quantity precision and bounds, reduce-only must not increase a position, `max_notional_per_order`, instrument min/max notional, cash balance impact for non-margin accounts, submit/modify rate limits, expiry sanity); the `TradingState` ladder ACTIVE/REDUCING/HALTED and its strict command permissions (in REDUCING only eligible reduce-only submits; in HALTED only cancels and queries); `OrderDenied` with reason codes; cancel/query bypass the engine; same engine in backtest, sandbox and live. Avoid: the `bypass` flag.

### 5.2 QuantConnect LEAN risk models ([docs](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/supported-models), [seen])
Six models: Null; MaximumDrawdownPercentPerSecurity (default 5% from entry); MaximumDrawdownPercentPortfolio (default 5%); MaximumUnrealizedProfitPercentPerSecurity (default 5%, lock gains); MaximumSectorExposure (default 20%, equities only); TrailingStop (5% from peak profit). Copy the *framework shape*: risk models are separate objects that post-process portfolio targets and can only liquidate or scale down. Gap: no FX/currency-factor exposure model; you must write USD-factor limits yourself.

### 5.3 Freqtrade protections ([docs](https://www.freqtrade.io/en/stable/plugins/), [seen])
StoplossGuard (N stoploss exits in a window locks trading; per-pair and per-side options), MaxDrawdown (`calculation_mode: "equity"` recommended; locks for a duration), LowProfitPairs (lock instruments with weak recent profit), CooldownPeriod (lock an instrument after exit). Copy: **time-boxed locks with lookback and unlock times** as the circuit-breaker primitive; equity-curve-based drawdown rather than trade-ratio approximation.

### 5.4 Lumibot ([README](https://github.com/Lumiwealth/lumibot), [seen])
README advises paper trading first and warns that software bugs can cause rapid losses; has an AGENTS.md "Production Safety" file (content not seen). The AI example enforces limits in the prompt (not a hard control) and shows a read-only reviewer agent. Copy: read-only agent role; do not copy prompt-based limits as controls.

### 5.5 Also worth noting
Knight Capital 2012: first SEC enforcement of Market Access Rule 15c3-5; ~$460M loss, >4M orders sent when trying to fill 212 customer orders, $12M penalty ([seen] SEC and law-firm summaries above). The rule's essence (pre-submission checks against capital/credit thresholds and erroneous-order checks) is the template for Layer A and Layer E.

---

## 6. Regime handling, metrics and monitoring

### 6.1 Regime detection used for de-risking (not for alpha)
- **Primary, simple, robust**: volatility regime from realized/EWMA vol relative to its own rolling percentile; risk multiplier m_regime = clip(sigma_target/sigma_hat, 0.25, 1) with hysteresis (enter de-risk at >90th pct, exit at <75th) to avoid whipsaw. Vol targeting as an *alpha* is contested (Section 1.1) but as a *risk dampener* it is defensible.
- **Correlation regime**: when average pairwise correlation across your book spikes above a threshold (e.g., > 0.7), cut cluster allowances. Gold in March 2020 fell (about 10% from 24 Feb to 16 Mar per [interactive investor](https://ii.co.uk/analysis-commentary/why-did-safe-haven-gold-fall-value-during-market-sell-ii512586); dollar strength and "forced liquidation across all assets including gold" as VaR models signaled cuts per [Refinitiv via Mining Weekly](https://www.miningweekly.com/article/recent-gold-plummet-the-result-of-multiple-factors-says-refinitiv-2020-04-21) and [LBMA](https://www.lbma.org.uk/alchemist/issue-98/is-gold-still-a-safe-haven-asset)). So "gold hedges equities" fails exactly when you need it.
- **HMM (hmmlearn) pitfalls** ([seen] tutorials/forum summary: [QuantConnect hmmlearn docs](https://www.quantconnect.com/docs/v2/research-environment/machine-learning/popular-libraries/hmmlearn), [QSTrader/QuantStart](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)): full-sample `predict`/Viterbi labels are *smoothed* and leak the future; lag regime signals at least one bar; state ordering is arbitrary (sort by volatility); fix random_state and test seed stability; refit on rolling/expanding windows and evaluate only out-of-sample. No rigorous walk-forward evidence surfaced in my search. Use HMM only as a secondary, **filtered** (not smoothed) signal that can only reduce risk.
- **Scheduled-event regime**: calendar blackout (Layer A) is the cleanest "regime" with no estimation error.

### 6.2 Risk metrics to compute locally and continuously
VaR/ES (historical, filtered-historical, and stressed), realized vol, drawdown (depth, duration, time-under-water), Sharpe/Sortino/Calmar, tail ratio, skew/kurtosis, MAE/MFE, turnover, cost/PnL ratio, factor exposures (USD, equity beta, rates). All available from QuantStats/empyrical-reloaded/ffn or ~100 lines of numpy.
- **Deflated Sharpe Ratio** (Bailey and López de Prado, J. Portfolio Management 2014; [SSRN 2460551](https://papers.ssrn.com/abstract=2460551), [seen]): adjusts Sharpe for selection bias under multiple testing and non-normality. Requires an estimate of the number of independent trials; López de Prado's 2018 book proposes clustering strategy variants to estimate it ([seen] secondary). **For this project: log every model/parameter trial** (the research platform will run many) so the DSR trial count is honest. I did not fetch the formula; implement from the paper.

### 6.3 Live-vs-backtest drift monitoring
- Track: realized slippage vs model, fill rate, spread paid, hit rate, average win/loss, trade frequency, PnL vs bootstrapped backtest distribution, feature/prediction distribution drift (PSI/KS), calibration drift of the classifier (Brier score/reliability curve).
- Triggers (starting points): slippage > 2x model for 20 fills => REDUCING; live rolling-60-trade expectancy below the backtest 5th percentile => halve size; live drawdown > 1.5x backtest 95th-percentile max DD => kill and post-mortem. A blog source advises after a 10% monthly drawdown to stop live, return to demo for 2 weeks and diagnose ([seen] search summary: [setup4alpha](https://setup4alpha.substack.com/p/how-to-go-live-with-a-trading-system-without-getting-drawdowns)). No source gave a rigorous statistical decay test; use sequential tests (CUSUM) as a design choice [bg].
- Graduated deployment [bg suggestion]: paper -> 10% size -> 25% -> 50% -> 100%, each stage gated by monitoring metrics.

### 6.4 Stress-test scenario library (deterministic, local)
Run on the *current* book daily; block entries if scenario loss > budget.

| Scenario | What happened ([seen] unless marked) | Parameterization for the engine |
|---|---|---|
| SNB, 2015-01-15 | CHF rose almost 30% against most majors; Alpari UK insolvent (administration 19 Jan); FXCM about $225M loss and $300M Leucadia loan; Interactive Brokers client losses about $120M; most retail brokers forgave negative balances ([Michelmores](https://www.michelmores.com/commercial-litigation-insight/swiss-franc-turbulence/), [FinanceMagnates](https://www.financemagnates.com/terms/s/swiss-national-bank-snb-crisis/), [IB losses](https://www.financemagnates.com/forex/brokers/interactive-brokers-suffers-120-million-client-losses-trading-uninterrupted/), [Fortune](https://fortune.com/2015/01/16/swiss-bombshell-leaves-blood-on-floor-from-new-york-to-new-zealand/)) | Pegged/managed-currency break: single-bar 20-30% gap with NO fills at stop; apply to any pair where a central-bank regime exists (CHF, DKK, HKD, CNH, etc.) |
| March 2020 | Gold fell about 10% (24 Feb-16 Mar) with dollar surge and cross-asset liquidation | Correlations -> 1, gold and equities down together, USD up 3-5% in a week |
| Jan 2026 silver/gold crash | Per [GoldSilver](https://goldsilver.com/industry-news/article/what-are-margin-requirements-why-cmes-hike-triggered-a-silver-crash/): silver peaked above $120, CME moved to percentage-based margins on 2026-01-13, margin hikes forced selling, silver fell into the $70s; on 2026-02-06 CME raised COMEX silver margin 15% to 18% and gold 8% to 9%. Other results claim gold fell 16% intraday and call it silver's worst day since 1980 ([MarketIndex](https://www.marketindex.com.au/news/gold-and-silver-suffer-historic-crash-wiping-usd7-trillion-heres-what-you), [Discovery Alert](https://discoveryalert.com.au/cme-gold-silver-margin-increase-2026/)). **[unverified]**: article is by a bullion dealer; other pages thinly sourced; confirm with CME notices and Reuters/Bloomberg | Metals: -15% gold / -30% silver in a day, plus margin requirement +50% overnight, plus spread 5x |
| Oct 2026 selloff | One low-quality source: gold -6.9% and silver -18.6% in October on a tech sell-off liquidation ([Discovery Alert](https://discoveryalert.com/analysis/gold-silver-sell-off-evidence-november-2026/)) **[unverified]** | Safe-haven liquidation alongside equity drawdown |
| Real-yield shock | US 10y real yield reached its highest in 20+ years at 2.63% ([seen] [Kitco 2026-09-22](https://www.kitco.com/news/article/2026-09-22/etf-flows-show-gold-price-decoupled-real-yields-fiscal-concerns-now-drive)) | +75bp real yields in a month with gold's beta to yields as an *uncertain* parameter (sample both signs) |
| Generic flash events | [bg: GBP Oct 2016 flash, 2010 equity flash crash, Aug 2015] not fetched | Spread blowout 10x, 1-3% gaps in minutes, stop slippage 5x |
| Broker/venue outage | [bg] | Cannot trade for N hours with positions open; rely on server-side stops |
| Data glitch | [seen anecdotal](https://www.tradingview.com/chart/BTCUSDT/qQQjxaWA-The-main-reason-you-re-blowing-up-accounts) bug/stale feed stories | Stale quote 5 min then jump |

---

## 7. Gold / silver / FX specifics

### 7.1 Gold vs USD, real yields, equities, and when it breaks
- Historical regularity [bg]: gold falls when real yields and the USD rise.
- **Break since 2022** ([seen] [Janus Henderson](https://www.janushenderson.com/social/article/chart-to-watch-whats-behind-the-divergence-between-gold-and-real-treasury-yields/), [Kitco 2026-09-22](https://www.kitco.com/news/article/2026-09-22/etf-flows-show-gold-price-decoupled-real-yields-fiscal-concerns-now-drive), [goldsilver.com](https://goldsilver.com/industry-news/article/gold-price-fed-rate-hike-2026-real-yields-decoupling/)): gold kept rising while real yields hit multi-decade highs; official-sector buying (WGC data cited: >1,000 t/yr in 2022-24, 863 t in 2025 vs 473 t 2010-21 average) is the commonly cited explanation, with fiscal-sustainability concerns as another. Janus argues real yields still set *short-horizon direction*. These are commentary sources; their attribution is not independently verified.
- Engineering implication: use **rolling, regime-aware** correlation estimates; do not hard-code a "gold = anti-USD hedge" assumption; in the USD-factor decomposition treat XAUUSD as short-USD *and* a separate safe-haven/real-rate factor; stress-test both signs.
- Gold also sells off in liquidity crunches (March 2020) and in margin-driven events (Jan 2026 reported). Silver is much more volatile than gold (Jan 2026 and Oct 2026 reports, [unverified] magnitudes), so size silver by its own ATR, not as "gold-ish".

### 7.2 FX carry and funding/swap costs
- Swap/rollover = interest differential adjustment for positions held past the broker's daily rollover (typically ~21:00 UTC); quoted in points, % or per-lot depending on the platform (MT4/MT5 `SYMBOL_SWAP_MODE`); triple swap normally on Wednesday for the weekend; broker markup on top of interbank rates; check the symbol spec ([seen] [Pepperstone](https://pepperstone.com/en-eu/learn-to-trade/trading-guides/what-are-swaps-how-to-calculate-swaps), [Eightcap](https://www.eightcap.com/labs/?p=2838), [AfterPrime](https://afterprime.com/glossary/triple-swap-wednesday), [FXNX](https://fxnx.com/en/blog/xauusd-swap-rates-table-nightly-long-short-cost-per-lot)). One illustrative gold example: long swap -65.50 points, 2 lots => -$131/night, -$393 on the triple night (broker unidentified) **[unverified]**.
- Engineering: model swap per instrument per side as a time-varying cost read from broker spec daily; include in (a) cost gate, (b) expected-holding-period P&L, (c) time-stop. Carry strategies are a famous source of "pick up pennies in front of a steamroller" tail risk [bg]; SNB 2015 (CHF funding trades) is the canonical example.
- Funding on **spot gold CFD** usually embeds a negative carry for longs [bg; broker dependent].

### 7.3 Leverage, margin calls, close-out, gaps, weekends
- ESMA retail CFD leverage limits: 30:1 major FX; 20:1 non-major FX, gold and major indices; 10:1 other commodities and non-major indices; 5:1 single equities; 2:1 crypto. Close-out when margin falls to 50% of minimum required margin; negative-balance protection per account ([seen] [ESMA](https://www.esma.europa.eu/press-news/esma-news/esma-agrees-prohibit-binary-options-and-restrict-cfds-protect-retail-investors)). These are EU rules (renewal in 3-month periods when temporary, per the page); your broker's jurisdiction determines which apply.
- US (CFTC/NFA): sources report 50:1 majors / 20:1 minors; metals limit conflicts across sources (10:1 vs 20:1) and I could not verify against an official source **[unverified]** ([BrokerChooser](https://brokerchooser.com/safety/leverage-margin-limits-us)). Whether exchange-traded gold futures are subject to these caps: not verified here.
- At margin call/close-out the broker closes positions at *market*, often at the worst moment (spreads wide, gaps); negative balance protection (where it exists) shifts the loss to the broker, which is why brokers failed in 2015.
- Weekend/gap: FX/metals close around Friday evening and reopen Sunday; gaps bypass stops. Starting rules: reduce gross by 30-50% into weekend or require position loss at a *gap-stressed* stop (e.g., 3x normal stop distance) to be within the risk budget; avoid holding into scheduled mega-events.

---

## 8. Capital-scale reality and prop-firm reference rule-set

### 8.1 What retail algo traders use (from non-primary sources)
- Per-trade risk about 1% as ceiling; 0.25-0.5% common among profitable traders ([seen] [CrossTrade](https://crosstrade.io/learn/risk-management/one-percent-rule), [Hackernoon](https://hackernoon.com/why-bet-size-kills-more-trading-accounts-than-bad-signals), [curvedtrading](https://curvedtrading.com/articles/en/how/risk-management-beginners/)).
- Daily stop about -3%; strategy kill about -15% drawdown; or "halve at 10%, stop at 20%" ([seen] search summaries); thresholds vary widely, none is a standard.
- A statistic circulating on vendor blogs ("85% who kept to 1-2% risk were still trading after two years; 88% risking 10%+ per position blew up within a year") is cited without a source in the Hackernoon piece and I could not verify it **[unverified]**.
- Arithmetic worth keeping (simple, [seen] on Hackernoon, and easy to verify yourself): 20 consecutive losses at 1% risk leaves ~82% of the account; 10 losses at 5% costs ~40%; a 50% drawdown needs +100% to recover.

### 8.2 US PDT status (verified for late 2026)
- SEC approved FINRA's Rule 4210 amendments on 2026-04-14 ([seen] [ThinkAdvisor](https://www.thinkadvisor.com/amp/2026/04/14/sec-approves-plan-removing-day-trading-limit-for-small-investors/), [Schwab](https://international.schwab.com/story/sec-approves-scrapping-25000-day-trader-minimum)). FINRA Regulatory Notice 26-10: effective 2026-06-04; members that need more time may phase in until 2027-10-20; the day-trade-count test and PDT designation and the **$25,000 minimum equity are eliminated**; replaced by an intraday margin standard (equity must cover exposure intraday; "intraday margin deficits" must be met promptly; 90-day restriction on opening new short/debit positions for habitual failure to meet deficits) ([seen] [FINRA 26-10](https://www.finra.org/rules-guidance/notices/26-10)). The notice sets no new fixed minimum for ordinary margin accounts; one broker summary (E*TRADE) lists $2,000, same as any margin account ([seen] via search; check your broker).
- Brokers are mid-rollout, so behavior differs by broker until late 2027. Cash accounts keep T+1/good-faith rules [bg]. Forex/CFD/spot metals are not under this rule [bg].

### 8.3 Prop-firm rule-set as a reference template
FTMO ([seen] [official trading objectives](https://ftmo.com/en/trading-objectives/)):
- 2-Step: 5% max daily loss, 10% static max loss (from initial capital), profit targets 10%/5%, 4 minimum trading days.
- 1-Step: 3% daily loss, 10% **trailing end-of-day** max loss, consistency rule (best day <= 50% of total profit for orders from 2026-10-12).
- Instant: 3% daily, 10% intraday trailing, 30% best-day rule.
- Daily limit = midnight (CE(S)T) balance minus the percentage; **breach check is on equity, so floating losses count in real time**.
Use as a template: (a) equity-based, real-time daily loss; (b) a trailing/static floor distinct from daily; (c) a best-day/consistency concept to flag lucky, non-repeatable returns; (d) internal limits at ~50-60% of the external numbers. If the system ever trades prop capital, the rules must be encoded in the gate as additional hard limits (external limits are *the* binding constraint there).

---

## 9. Community findings (and what was not reachable)

**Reachability:**
- Reddit (r/algotrading, r/quant, r/Forex, r/options): **not reachable.** WebFetch refused `reddit.com`/`old.reddit.com`; `site:reddit.com` searches returned zero Reddit results across several tries.
- Hacker News: Algolia API reachable, but queries ("kelly criterion trading", "algorithmic trading risk management lost") returned irrelevant items (a Show HN investing-models post with 1 point; an unrelated Launch HN). No usable HN discussion found.
- X/Twitter and Instagram: not reachable/not findable via search tools.
- YouTube: only transcript/summary aggregator pages surfaced, not channel content.
So the community picture below is from forums (NexusFi, MQL5), blogs and press; treat as lower-quality than primary threads.

**Themes ([seen], search-result level):**
- Blow-ups are fast and sizing-driven: "almost all blown-up accounts happen quickly, typically from only 1-3 trades"; all-in sizing and ignored stops ([TradingView post](https://br.tradingview.com/chart/BTCUSDT/qQQjxaWA-The-main-reason-you-re-blowing-up-accounts)). "Bet size is what kills accounts, not bad signals" ([Hackernoon](https://hackernoon.com/why-bet-size-kills-more-trading-accounts-than-bad-signals)).
- High win-rate with poor reward/risk blew up an account ([NexusFi thread](https://nexusfi.com/psychology-money-management/57078-i-finally-blew-up-account-13.html)); moderators argue a 100+ trade-proven strategy that loses is a discipline/risk problem ([NexusFi](https://nexusfi.com/showthread.php?p=841297)).
- Moving stops away is called worse than no stop ([work-club](https://work-club.com/trading-mistakes-risk-management/amp/)).
- Algo-specific: backtests with high profit factors disappoint live; a feed outage left a bot with no signals; a dataset-mixing bug applied one data set to another ([TradingView posts](https://jp.tradingview.com/chart/BTCUSD/vejttFBY-How-Algo-Bots-Target-Retail-SL-Learn-to-Beat-Them) and others via search). Lessons: data-integrity checks, reconciliation, and live-vs-backtest monitors (Layer E).
- "Risk management is the only real alpha" style posts ([MQL5 blog](https://www.mql5.com/en/blogs/post/771741), [DEV](https://dev.to/timevolt/risk-management-in-algo-trading-lessons-from-the-matrix-311m)) agree with the layered approach but provide no numbers beyond 1-2% rules.
- Kelly debate (non-Reddit sources only): consensus is "fractional, quarter-to-half, never trust your p" ([questdb](https://questdb.com/glossary/kelly-criterion-for-optimal-betting), [arXiv 2010.12508](https://arxiv.org/pdf/2010.12508), [Philipp Dubach "Bet Sizing at the Frontier"](https://philippdubach.com/posts/bet-sizing-at-the-frontier/) (title only seen)).
- Rules people say they wish they had (synthesized from the above): hard daily loss limit, size from current equity, no averaging down, automatic halt on anomalies, never trade through high-impact news with a small account, check swaps before holding, and know your broker's margin close-out and negative-balance policy.

---

## 10. Open questions

1. Which brokers/venues? (OANDA/IBKR/Pepperstone-type CFD vs US stock brokers vs futures) determines leverage caps, NBP, swap schedule, contract sizes, API for server-side stops, and whether the dead-man flatten exists.
2. Is trading *prop* capital in scope? If so, the prop rules become additional hard limits (Section 8.3).
3. How is the profitability classifier calibrated, and per what horizon? Sizing quality depends on calibration (Section 1.1).
4. Edge-estimation procedure for Kelly ceiling: Bayesian shrinkage vs bootstrap lower bound (need design decision).
5. Method for Omega calibration of LLM views (per-view-type hit-rate tracking requires months of data).
6. Which regime signals are allowed to *relax* risk (the proposal: none; only tighten)? Is a slow, human-reviewed relax path desirable?
7. Verify jan-2026 silver/gold crash figures with CME notices and Reuters/Bloomberg before building scenario parameters from them.
8. Verify last-commit/maintenance for Nautilus, LEAN, Freqtrade, Lumibot, hmmlearn; verify Apple Silicon support for LEAN, MOSEK, hmmlearn.
9. Verify AFML ch.10 formulas against the book; verify DSR formula against the paper.
10. CFTC/NFA metals leverage and futures-vs-spot treatment: verify with NFA documents.
11. Intraday-margin implementation details per US broker after FINRA 26-10 (broker-specific).

---

## 11. Local-first stack (new constraint)

**Constraint:** only Anthropic Claude models may be cloud LLMs; all else local on Apple Silicon.

### 11.1 What runs where

| Component | Where | Network needed? | Notes |
|---|---|---|---|
| Risk gate (limits, sizing, circuit breakers, kill switch) | Local, separate process | Only the broker link; **never** the Claude API | Pure Python (numpy/pandas/scipy) or Rust (Nautilus' RiskEngine path) |
| Sizing (ATR, vol targeting, fractional-Kelly ceiling, AFML map) | Local | No | numpy |
| Covariance/shrinkage/HRP/ERC/CVaR/BL | Local | No | skfolio, Riskfolio-Lib, PyPortfolioOpt, cvxportfolio on cvxpy with open solvers Clarabel/OSQP/SCS/HiGHS; no commercial solver needed for retail-scale problems |
| Regime / vol / correlation monitors | Local | No | numpy/hmmlearn (optional) |
| Stress tests, VaR/ES, DSR, drift monitors | Local | No | numpy, QuantStats/empyrical-reloaded |
| State store, audit log | Local SQLite/Parquet | No | |
| Calendar, rates, FX conversion | Local cache refreshed when online | Refresh only | Stale cache => conservative fallback |
| Claude (views, explanations) | Anthropic cloud | Yes | Outside the safety path |

Apple Silicon: cvxpy ships universal2 (ARM64) wheels and depends on open solvers; the portfolio libraries are Python on top of numpy/scipy/cvxpy so they are expected to run natively on Apple Silicon (**not individually verified**; test with a smoke-test CI on the target Mac). NautilusTrader lists macOS ARM64 wheels. MOSEK/Gurobi arm64 macOS and LEAN on Apple Silicon: **unverified**; avoid depending on them.

### 11.2 Where Claude may sit
- **Allowed (advisory):** structured Black-Litterman views {asset, direction, expected return (capped), confidence, TTL, rationale}; news/event summarization into *additional* blackout proposals; scenario narratives for stress-test design; plain-language explanations of risk reports and drift alerts; post-mortem drafts after circuit-breaker events; suggestions for parameter reviews (human approves).
- **Forbidden:** direct order placement, holding broker credentials, modifying/disabling limits, removing blackouts, overriding a gate rejection, being a runtime dependency of the gate or kill switch.
- **Failure modes handled:** Claude API outage (views expire, portfolio decays to neutral prior, no new LLM-driven entries); prompt injection via news (bounded schema, tighten-only authority, view magnitude caps); LLM hallucination (view track-record scoring; Omega derived from measured accuracy; views from an unscored generator get a large Omega floor).
- **Asymmetry rule:** any Claude-originated message may only (a) propose within bounds that the gate re-validates, or (b) make the system *more* conservative. Loosening is human-only.

### 11.3 Local-first acceptance tests (suggested)
1. Disable network and Claude API: gate approves/rejects deterministically; open positions keep server-side stops; kill switch works.
2. Kill the risk process: execution adapter refuses orders (no gate lease).
3. Feed adversarial LLM output (oversized views, malformed JSON, "ignore limits" text): all clipped/rejected, no limit change.
4. Replay SNB-2015, March-2020 and Jan-2026-style shocks through the gate in backtest with the same code path as live.
5. Corrupt limits file/hash: gate HALTs.
6. Reconciliation drift (local state != broker): HALT.

---

## Appendix: Source index (cited above)

- FINRA Reg Notice 26-10: https://www.finra.org/rules-guidance/notices/26-10
- SEC approval coverage: https://www.thinkadvisor.com/amp/2026/04/14/sec-approves-plan-removing-day-trading-limit-for-small-investors/ ; https://international.schwab.com/story/sec-approves-scrapping-25000-day-trader-minimum
- FTMO rules: https://ftmo.com/en/trading-objectives/
- ESMA CFD measures: https://www.esma.europa.eu/press-news/esma-news/esma-agrees-prohibit-binary-options-and-restrict-cfds-protect-retail-investors
- Kelly: https://en.wikipedia.org/wiki/Kelly_criterion ; https://questdb.com/glossary/kelly-criterion-for-optimal-betting ; https://arxiv.org/pdf/2010.12508
- AFML ch.10 secondary: https://www.mql5.com/en/articles/21824 ; https://www.mql5.com/en/articles/21938
- HRP: https://en.wikipedia.org/wiki/Hierarchical_Risk_Parity
- Shrinkage: https://scikit-learn.org/stable/modules/covariance.html
- DSR: https://papers.ssrn.com/abstract=2460551
- LLM-BL: https://arxiv.org/abs/2504.14345
- Nautilus risk: https://nautilustrader.io/docs/latest/concepts/execution/
- LEAN risk: https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/supported-models
- Freqtrade protections: https://www.freqtrade.io/en/stable/plugins/
- Lumibot: https://github.com/Lumiwealth/lumibot
- Library repos: Riskfolio-Lib, skfolio, PyPortfolioOpt, cvxportfolio, quantstats, empyrical-reloaded, pyfolio-reloaded, bt, ffn, vectorbt (links in Section 4.2)
- Knight Capital: https://www.sec.gov/news/press-release/2013-222 ; https://www.wilmerhale.com/en/insights/client-alerts/knight-capital-settles-rule-15c3-5-violations-with-sec-agrees-to-pay-12-million
- SNB 2015: https://www.michelmores.com/commercial-litigation-insight/swiss-franc-turbulence/ ; https://www.financemagnates.com/terms/s/swiss-national-bank-snb-crisis/ ; https://fortune.com/2015/01/16/swiss-bombshell-leaves-blood-on-floor-from-new-york-to-new-zealand/
- Gold/real yields: https://www.kitco.com/news/article/2026-09-22/etf-flows-show-gold-price-decoupled-real-yields-fiscal-concerns-now-drive ; https://www.janushenderson.com/social/article/chart-to-watch-whats-behind-the-divergence-between-gold-and-real-treasury-yields/
- Metals crash 2026: https://goldsilver.com/industry-news/article/what-are-margin-requirements-why-cmes-hike-triggered-a-silver-crash/ (plus lower-quality: marketindex, discoveryalert)
- March 2020 gold: https://ii.co.uk/analysis-commentary/why-did-safe-haven-gold-fall-value-during-market-sell-ii512586 ; https://www.lbma.org.uk/alchemist/issue-98/is-gold-still-a-safe-haven-asset ; https://www.miningweekly.com/article/recent-gold-plummet-the-result-of-multiple-factors-says-refinitiv-2020-04-21
- Swaps: https://pepperstone.com/en-eu/learn-to-trade/trading-guides/what-are-swaps-how-to-calculate-swaps ; https://afterprime.com/glossary/triple-swap-wednesday
- Vol-managed portfolios (via search summary): https://lbsresearch.london.edu/id/eprint/3716
- cvxpy wheels: https://pypi.org/project/cvxpy/
