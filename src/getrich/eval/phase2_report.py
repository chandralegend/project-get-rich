"""Run the PI-Net v1 models on the real BTC and ETH dataset and report them against the baselines.

Each model runs in its own process (see pinet_worker.py). This parent process never imports PyTorch or
LightGBM. Every model is evaluated through the same 6-group, 2-test-group CPCV (5 out-of-sample paths) with
a 6-day embargo, then judged at base and 2x costs, and counted as a trial for the Deflated Sharpe.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import pinet_eval
from .costs import CostModel
from .data import load_bars
from .features import Dataset, make_dataset

MODELS = ("linear", "lgbm", "fusion")


def label_summary(ds: Dataset) -> dict:
    import pandas as pd

    kinds = pd.Series(dtype=float)
    return {
        "rows": len(ds), "assets": sorted(set(ds.asset)),
        "start": str(ds.bar.min().date()), "end": str(ds.bar.max().date()),
        "base_rate": float(ds.y.mean()), "mean_r_net": float(ds.r_net.mean()), "mean_cost_r": float(ds.cost_r.mean()),
        "mean_r_net_2x": float(ds.r_at(2.0).mean()),
    }


def run_worker(model: str, n_null: int, out: Path) -> None:
    cmd = [sys.executable, "-I", "-m", "getrich.eval.pinet_worker", "--model", model, "--out", str(out), "--null", str(n_null)]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    sys.stderr.write(proc.stderr[-600:])
    if proc.returncode != 0:
        raise RuntimeError(f"worker for {model} failed:\n{proc.stderr[-1500:]}")


def run(null_counts: dict[str, int] | None = None, cost: CostModel | None = None) -> dict:
    cost = cost or CostModel()
    null_counts = null_counts or {"linear": 100, "lgbm": 40, "fusion": 0}
    ds = make_dataset(cost=cost)
    closes = {s: load_bars(s, "1d")["close"] for s in sorted(set(ds.asset))}
    results, extras = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for model in MODELS:
            out = Path(tmp) / f"{model}.npz"
            run_worker(model, null_counts.get(model, 0), out)
            z = np.load(out, allow_pickle=True)
            if not np.array_equal(z["t0"], ds.t0.astype("int64")) or not np.array_equal(z["asset"], ds.asset):
                raise RuntimeError(f"{model}: worker row order differs from the parent dataset")
            results.append(pinet_eval.evaluate_model(model, list(z["preds"]), ds, closes, cost))
            extras[model] = {"real_score": float(z["real_score"]), "p_value": float(z["p_value"]), "n_null": int(len(z["null_scores"]))}
    summary = pinet_eval.summarize(results, pinet_eval.baseline_returns(ds, closes, cost),
                                   pinet_eval.baseline_returns(ds, closes, cost.stressed(2.0)))
    for row in summary["models"]:
        row.update(extras[row["name"]])
    return {"summary": summary, "labels": label_summary(ds), "cost": cost}


def _pct(x, nd=1):
    return "n/a" if x != x else f"{x * 100:.{nd}f}%"


def to_markdown(res: dict) -> str:
    L, s, c = res["labels"], res["summary"], res["cost"]
    out = [
        "# Phase 2 results: PI-Net v1 on market and forecast channels",
        "",
        f"Dataset: {L['rows']} candidate long trades ({', '.join(L['assets'])}), decisions from {L['start']} to {L['end']}. "
        f"Triple-barrier: take-profit 2 sigma, stop 1 sigma, 10-day horizon. Costs {c.fee_bps:g}+{c.slippage_bps:g} bps per side (assumed) and 2x.",
        f"Taking every candidate trade averages {L['mean_r_net']:+.3f} R at base costs and {L['mean_r_net_2x']:+.3f} R at 2x; "
        f"{L['base_rate'] * 100:.0f}% of trades end with positive net R; mean round-trip cost {L['mean_cost_r']:.3f} R.",
        "",
        "Evaluation: 6-group combinatorial purged CV (2 test groups), 6-day embargo, 5 complete out-of-sample paths. "
        "Strategy mapping: hold each asset long while the model's expected net R is positive. Mean across paths, with the worst and best path.",
        "",
        "## Models against the baselines (portfolio of BTC and ETH sleeves, net of costs)",
        "",
        "| | Sharpe (mean, min to max) | Sharpe at 2x costs | CAGR | Max DD | Time long | Excess R per trade taken | at 2x | Deflated Sharpe | Null p-value |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s["models"]:
        p = "not run" if r["n_null"] == 0 else f"{r['p_value']:.3f} ({r['n_null']} draws)"
        out.append(
            f"| model: {r['name']} | {r['sharpe_mean']:.2f} ({r['sharpe_min']:.2f} to {r['sharpe_max']:.2f}) | {r['sharpe_2x_mean']:.2f} | "
            f"{_pct(r['cagr_mean'])} | {_pct(r['max_dd_mean'])} | {_pct(r['exposure'], 0)} | {r['trade_score_mean']:+.3f} | "
            f"{r['trade_score_2x_mean']:+.3f} | {r['dsr_mean']:.2f} | {p} |"
        )
    for b in s["baselines"]:
        out.append(f"| baseline: {b['name']} | {b['sharpe']:.2f} | {b['sharpe_2x']:.2f} | {_pct(b['cagr'])} | {_pct(b['max_dd'])} | n/a | n/a | n/a | {b['dsr']:.2f} | n/a |")
    out += ["", f"Deflated Sharpe counts {s['n_trials']} trials (the three models and the two baselines). "
            "'Excess R per trade taken' is the harness score: mean net R of trades the model takes minus the mean of taking every candidate; zero means no skill.", ""]
    return "\n".join(out)
