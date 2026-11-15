"""Pre-registered study (docs/preregistration-portfolio.md): do simple trend and momentum rules across 16 coins beat holding?

Every strategy is a plain rule with fixed textbook parameters; nothing is fitted. Weights for day t use data up to the close of
day t and are held over day t+1 (eval.backtest). The same cost model as everywhere else, shown at 1x and 2x.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config
from ..obs.events import emit
from . import baselines, metrics, trials
from .backtest import run as backtest_run
from .channel_ablation import prereg_events, prereg_hash
from .costs import CostModel
from .data import load_bars

PREREG = "docs/preregistration-portfolio.md"
UNIVERSE = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LTCUSDT", "DOTUSDT", "ADAUSDT", "BCHUSDT", "LINKUSDT", "XLMUSDT", "DOGEUSDT",
            "UNIUSDT", "EOSUSDT", "TRXUSDT", "XTZUSDT", "VETUSDT")
MIN_HISTORY = 256
BAND = 0.05
TARGET_VOL = 0.25
TOP_K = 5
START = pd.Timestamp("2021-01-30", tz="UTC")
STRATEGIES = ("S0", "S1", "S2", "S3", "S4")
NAMES = {"S0": "equal-weight hold", "S1": "trend, equal weight", "S2": "trend, risk parity", "S3": "trend, volatility target", "S4": "momentum, top 5"}
MIN_SHARPE_GAIN, MIN_DSR, MAX_DD = 0.10, 0.90, 0.40
EXPOSURE_CAP = 0.20     # the approved "minimal" profile


def eligible(close: pd.DataFrame) -> pd.DataFrame:
    """A coin counts once it has MIN_HISTORY bars, and only while it still has a bar."""
    return close.notna() & (close.notna().cumsum() >= MIN_HISTORY)


def signals(close: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for c in close.columns:
        s = close[c].dropna()
        out[c] = baselines.trend_signal(s).reindex(close.index) if len(s) else pd.Series(np.nan, index=close.index)
    return pd.DataFrame(out)[close.columns]


def weights(close: pd.DataFrame) -> dict[str, pd.DataFrame]:
    elig = eligible(close)
    n = elig.sum(axis=1).replace(0, np.nan)
    sig = signals(close).where(elig, 0.0).fillna(0.0)
    ret = close.pct_change()
    w = {}
    w["S0"] = elig.astype(float).div(n, axis=0).fillna(0.0)
    w["S1"] = sig.div(n, axis=0).fillna(0.0)
    vol = pd.DataFrame({c: baselines.ewma_vol(close[c].dropna()).reindex(close.index) for c in close.columns})
    inv = (sig / vol).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    tot = inv.sum(axis=1).replace(0, np.nan)
    budget = sig.sum(axis=1).div(n).clip(upper=1.0)
    w["S2"] = inv.div(tot, axis=0).mul(budget, axis=0).fillna(0.0)
    port = (w["S1"].shift(1) * ret.fillna(0.0)).sum(axis=1)
    realised = port.rolling(60, min_periods=60).std() * np.sqrt(metrics.DAYS_PER_YEAR)
    scale = (TARGET_VOL / realised).clip(upper=1.0).fillna(0.0)
    w["S3"] = w["S1"].mul(scale, axis=0)
    cand = elig & (sig >= 2 / 3 - 1e-9)
    rank = close.pct_change(90).where(cand).rank(axis=1, ascending=False, method="first")
    w["S4"] = (rank <= TOP_K).astype(float) / TOP_K
    return w


def portfolio_returns(close: pd.DataFrame, w: pd.DataFrame, cost: CostModel) -> pd.DataFrame:
    net = pd.Series(0.0, index=close.index)
    gross, paid, expo = net.copy(), net.copy(), net.copy()
    for c in close.columns:
        s = close[c].dropna()
        if len(s) < 3:
            continue
        bt = backtest_run(s, w[c].reindex(s.index).fillna(0.0), cost, band=BAND)
        net = net.add(bt["net"].reindex(close.index).fillna(0.0), fill_value=0.0)
        gross = gross.add(bt["gross"].reindex(close.index).fillna(0.0), fill_value=0.0)
        paid = paid.add(bt["cost"].reindex(close.index).fillna(0.0), fill_value=0.0)
        expo = expo.add(bt["position"].reindex(close.index).fillna(0.0), fill_value=0.0)
    return pd.DataFrame({"net": net, "gross": gross, "cost": paid, "exposure": expo})


def block_bootstrap_diff(a: np.ndarray, b: np.ndarray, block: int = 20, reps: int = 1000, seed: int = 0) -> dict:
    """Moving-block bootstrap of the Sharpe difference a minus b on paired days."""
    n = len(a)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    diffs = np.empty(reps)
    for i in range(reps):
        idx = np.concatenate([np.arange(s, s + block) % n for s in rng.integers(0, n, nb)])[:n]
        diffs[i] = metrics.sharpe(a[idx]) - metrics.sharpe(b[idx])
    return {"lo": float(np.percentile(diffs, 2.5)), "hi": float(np.percentile(diffs, 97.5)), "p_better": float((diffs > 0).mean())}


def load_close(symbols=UNIVERSE) -> pd.DataFrame:
    cols = {s: load_bars(s, "1d")["close"] for s in symbols}
    close = pd.DataFrame(cols).sort_index()
    close.index = close.index.normalize()
    return close


def run(close: pd.DataFrame | None = None, cost: CostModel | None = None, register: bool = True, require_prereg: bool = True) -> dict:
    h = prereg_hash(PREREG) if require_prereg else None
    if require_prereg and h not in {e.get("sha256") for e in prereg_events()}:
        raise RuntimeError("the portfolio pre-registration does not match any logged hash: run `getrich preregister docs/preregistration-portfolio.md`")
    cost = cost or CostModel()
    close = load_close() if close is None else close
    w = weights(close)
    res, base1, base2 = {}, {}, {}
    for k in STRATEGIES:
        base1[k] = portfolio_returns(close, w[k], cost)
        base2[k] = portfolio_returns(close, w[k], cost.stressed(2.0))
    btc = close["BTCUSDT"].pct_change().fillna(0.0)
    window = close.index >= START
    mid = close.index[window][len(close.index[window]) // 2]
    new_period = [float(base1[k]["net"][window].mean() / base1[k]["net"][window].std(ddof=1)) for k in STRATEGIES]
    all_trials = trials.period_sharpes() + new_period
    bench2 = {"S0": base2["S0"]["net"][window].to_numpy(), "BTC buy and hold": btc[window].to_numpy()}
    for k in STRATEGIES:
        r1, r2 = base1[k]["net"][window].to_numpy(), base2[k]["net"][window].to_numpy()
        idx = close.index[window]
        first, second = idx < mid, idx >= mid
        years = pd.Series(r1, index=idx).groupby(idx.year).apply(lambda x: float(np.prod(1 + x) - 1)).to_dict()
        row = {"name": NAMES[k], "sharpe": metrics.sharpe(r1), "sharpe_2x": metrics.sharpe(r2), "cagr": metrics.cagr(r1), "max_dd": metrics.max_drawdown(r1),
               "exposure": float(base1[k]["exposure"][window].mean()), "turnover_cost_a_year": float(base1[k]["cost"][window].sum() / (len(r1) / 365)),
               "half1_2x": metrics.sharpe(r2[first]), "half2_2x": metrics.sharpe(r2[second]), "years": years, "dsr": metrics.deflated_sharpe(r1, all_trials),
               "scaled_cagr": metrics.cagr(r1 * EXPOSURE_CAP), "scaled_dd": metrics.max_drawdown(r1 * EXPOSURE_CAP)}
        row["dollars_a_year_500"] = 500.0 * row["scaled_cagr"]
        if k != "S0":
            row["vs"] = {b: block_bootstrap_diff(r2, x) for b, x in bench2.items()}
            gains = {b: row["sharpe_2x"] - metrics.sharpe(x) for b, x in bench2.items()}
            row["gains"] = gains
            row["criteria"] = {"gain_vs_both": all(g >= MIN_SHARPE_GAIN for g in gains.values()), "dsr": row["dsr"] >= MIN_DSR,
                               "both_halves_positive": row["half1_2x"] > 0 and row["half2_2x"] > 0, "drawdown": row["max_dd"] <= MAX_DD}
            row["shows_value"] = all(row["criteria"].values())
        res[k] = row
    refs = {"BTC buy and hold": {"sharpe": metrics.sharpe(btc[window]), "sharpe_2x": metrics.sharpe(btc[window]), "cagr": metrics.cagr(btc[window]), "max_dd": metrics.max_drawdown(btc[window])}}
    if register:
        for k in STRATEGIES:
            trials.register(4, f"portfolio-v1:{k}", res[k]["sharpe"], "docs/portfolio-study.md")
    emit("eval.portfolio_study_run", service="eval", prereg_sha256=h, n_trials=len(all_trials), shows_value={k: res[k].get("shows_value") for k in STRATEGIES})
    return {"rows": res, "refs": refs, "n_trials": len(all_trials), "prereg": h, "start": str(close.index[window][0].date()), "end": str(close.index[-1].date()),
            "coins": {c: int(close[c].notna().sum()) for c in close.columns}, "mid": str(mid.date()), "avg_eligible": float(eligible(close)[window].sum(axis=1).mean())}


def _pct(x, nd=1):
    return "n/a" if x != x else f"{x * 100:.{nd}f}%"


def to_markdown(res: dict) -> str:
    R = res["rows"]
    L = ["# Wider-universe trend and momentum study (pre-registered)", "",
         f"Pre-registration: `{PREREG}`, SHA-256 `{(res['prereg'] or 'unchecked')[:16]}...` (matches the hash logged before the run).",
         f"{len(res['coins'])} coins (about {res['avg_eligible']:.0f} eligible on an average day), {res['start']} to {res['end']}, halves split at {res['mid']}. "
         f"Deflated Sharpe counts {res['n_trials']} trials. Survivorship bias flatters every long-only row; it cannot be removed with free data.", "",
         "| | Sharpe | at 2x costs | CAGR | Max DD | Avg exposure | Half 1 / half 2 at 2x | Deflated Sharpe | Gain vs hold-all, vs BTC (2x) | Shows value? |",
         "|---|---:|---:|---:|---:|---:|---|---:|---|---|"]
    for k in STRATEGIES:
        r = R[k]
        if k == "S0":
            L.append(f"| {k} {r['name']} | {r['sharpe']:.2f} | {r['sharpe_2x']:.2f} | {_pct(r['cagr'])} | {_pct(r['max_dd'])} | {_pct(r['exposure'], 0)} | {r['half1_2x']:.2f} / {r['half2_2x']:.2f} | {r['dsr']:.2f} | benchmark | n/a |")
            continue
        c = r["criteria"]
        verdict = "**YES**" if r["shows_value"] else "no (" + ", ".join(x for x, ok in c.items() if not ok) + " failed)"
        g = r["gains"]
        L.append(f"| {k} {r['name']} | {r['sharpe']:.2f} | {r['sharpe_2x']:.2f} | {_pct(r['cagr'])} | {_pct(r['max_dd'])} | {_pct(r['exposure'], 0)} | "
                 f"{r['half1_2x']:.2f} / {r['half2_2x']:.2f} | {r['dsr']:.2f} | {g['S0']:+.2f}, {g['BTC buy and hold']:+.2f} | {verdict} |")
    b = res["refs"]["BTC buy and hold"]
    L.append(f"| reference: BTC buy and hold | {b['sharpe']:.2f} | {b['sharpe_2x']:.2f} | {_pct(b['cagr'])} | {_pct(b['max_dd'])} | 100% | | | | |")
    L += ["", "## Calendar years (base costs, full exposure)", "", "| | " + " | ".join(str(y) for y in sorted(R["S0"]["years"])) + " |", "|---|" + "---:|" * len(R["S0"]["years"])]
    for k in STRATEGIES:
        L.append(f"| {k} {R[k]['name']} | " + " | ".join(_pct(R[k]["years"][y]) for y in sorted(R[k]["years"])) + " |")
    L += ["", "## Bootstrap of the Sharpe difference at 2x costs (95% interval; share of draws where the strategy is ahead)", "", "| | vs equal-weight hold | vs BTC buy and hold |", "|---|---|---|"]
    for k in STRATEGIES[1:]:
        v = R[k]["vs"]
        L.append(f"| {k} {R[k]['name']} | {v['S0']['lo']:+.2f} to {v['S0']['hi']:+.2f} ({v['S0']['p_better'] * 100:.0f}%) | "
                 f"{v['BTC buy and hold']['lo']:+.2f} to {v['BTC buy and hold']['hi']:+.2f} ({v['BTC buy and hold']['p_better'] * 100:.0f}%) |")
    L += ["", f"## What it means in dollars on $500 under the approved limits (exposure capped at {EXPOSURE_CAP * 100:.0f}% of equity)", "",
          "| | CAGR at the cap | Dollars a year on $500 | Max drawdown at the cap |", "|---|---:|---:|---:|"]
    for k in STRATEGIES:
        L.append(f"| {k} {R[k]['name']} | {_pct(R[k]['scaled_cagr'])} | ${R[k]['dollars_a_year_500']:.0f} | {_pct(R[k]['scaled_dd'])} |")
    L += ["", f"Criteria (all required, for each of S1 to S4): Sharpe at 2x costs at least {MIN_SHARPE_GAIN:.2f} above BOTH hold-all and BTC buy and hold, Deflated Sharpe at least {MIN_DSR}, "
          f"positive Sharpe at 2x costs in both halves, maximum drawdown at most {MAX_DD * 100:.0f}% at full exposure.", "",
          "Caveats: the 5% no-trade band lets held weights drift, so average exposure can exceed the target (S0 averages above 100%), which slightly flatters S0 and is the reason it is a conservative benchmark. "
          "Survivorship bias flatters all rows. One crypto cycle, so differences under about 0.3 Sharpe are inside the noise (see the bootstrap intervals).", ""]
    return "\n".join(L)
