"""Run the PRE-REGISTERED meta-label experiment (docs/preregistration-meta-label.md) and judge it by its own criteria.

The geometry, models, folds and success criteria are fixed in the pre-registration and in pinet_worker.META_KWARGS.
Nothing here tunes anything. The Deflated Sharpe uses the cumulative trial registry (docs/trials.json), so it is
deflated against every variant tried in every phase, then the four new trials are added to the registry.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from .. import config
from ..obs.events import emit
from . import pinet_eval, trials
from .costs import CostModel
from .data import load_bars
from .features import make_dataset
from .pinet_worker import META_KWARGS

MODELS = ("linear", "lgbm", "fusion")
MIN_SHARPE_GAIN = 0.10      # criterion 1
MAX_P = 0.05                # criterion 2
MIN_DSR = 0.90              # criterion 3
PREREG = "docs/preregistration-meta-label.md"


def _worker(model: str, n_null: int, out: Path) -> None:
    cmd = [sys.executable, "-I", "-m", "getrich.eval.pinet_worker", "--model", model, "--meta", "--out", str(out), "--null", str(n_null)]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    sys.stderr.write(proc.stderr[-300:])
    if proc.returncode != 0:
        raise RuntimeError(f"worker for {model} failed:\n{proc.stderr[-1500:]}")


def run(null_counts: dict[str, int] | None = None, cost: CostModel | None = None, register: bool = True) -> dict:
    cost = cost or CostModel()
    null_counts = null_counts or {"linear": 100, "lgbm": 40, "fusion": 20}
    prereg_hash = hashlib.sha256(Path(config.root(), PREREG).read_bytes()).hexdigest()
    logged = {e.get("sha256") for e in _prereg_events()}
    if prereg_hash not in logged:
        raise RuntimeError("the pre-registration file does not match any logged hash: it was changed after being registered")

    ds = make_dataset(cost=cost, **META_KWARGS)
    closes = {s: load_bars(s, "1d")["close"] for s in sorted(set(ds.asset))}
    results, extras = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for model in MODELS:
            out = Path(tmp) / f"{model}.npz"
            _worker(model, null_counts.get(model, 0), out)
            z = np.load(out, allow_pickle=True)
            if not np.array_equal(z["t0"], ds.t0.astype("int64")) or not np.array_equal(z["asset"], ds.asset):
                raise RuntimeError(f"{model}: worker row order differs from the parent dataset")
            results.append(pinet_eval.evaluate_model(f"meta:{model}", list(z["preds"]), ds, closes, cost))
            extras[f"meta:{model}"] = {"p_value": float(z["p_value"]), "n_null": int(len(z["null_scores"]))}

    take_all = np.ones((len(ds), 2))
    alone = pinet_eval.evaluate_model("primary_alone", [take_all], ds, closes, cost)
    stressed = cost.stressed(2.0)
    base = pinet_eval.baseline_returns(ds, closes, cost)
    base["primary_alone"] = pinet_eval.model_returns(ds, take_all, closes, cost)
    base_2x = pinet_eval.baseline_returns(ds, closes, stressed)
    base_2x["primary_alone"] = pinet_eval.model_returns(ds, take_all, closes, stressed)

    new_period = [float(np.mean([p["sharpe_period"] for p in r["paths"]])) for r in results] + [float(base["primary_alone"].mean() / base["primary_alone"].std(ddof=1))]
    all_trials = trials.period_sharpes() + new_period
    summary = pinet_eval.summarize(results, base, base_2x, trial_sharpes=all_trials)
    alone_2x = next(b for b in summary["baselines"] if b["name"] == "primary_alone")["sharpe_2x"]
    for row in summary["models"]:
        row.update(extras[row["name"]])
        gain = row["sharpe_2x_mean"] - alone_2x
        row["sharpe_gain_2x"] = gain
        row["criteria"] = {"sharpe_gain": gain >= MIN_SHARPE_GAIN, "p_value": row["p_value"] < MAX_P, "dsr": row["dsr_mean"] >= MIN_DSR}
        row["shows_value"] = all(row["criteria"].values())
    if register:
        for r in summary["models"]:
            trials.register(3, f"meta-trend-v1:{r['name'].split(':')[1]}", r["sharpe_mean"], "docs/phase3-meta-results.md")
        pa = next(b for b in summary["baselines"] if b["name"] == "primary_alone")
        trials.register(3, "meta-trend-v1:primary_alone", pa["sharpe"], "docs/phase3-meta-results.md")
    emit("eval.meta_label_run", service="eval", prereg_sha256=prereg_hash, n_trials=len(all_trials),
         shows_value={r["name"]: r["shows_value"] for r in summary["models"]})
    return {"summary": summary, "rows": len(ds), "n_trials": len(all_trials), "prereg": prereg_hash, "cost": cost,
            "base_rate": float(ds.y.mean()), "mean_r": float(ds.r_net.mean()), "mean_r_2x": float(ds.r_at(2.0).mean()),
            "start": str(ds.bar.min().date()), "end": str(ds.bar.max().date())}


def _prereg_events() -> list[dict]:
    import json

    out = []
    for p in sorted(config.logs_dir().glob("events-*.jsonl")):
        for line in p.read_text().splitlines():
            if '"eval.preregistered"' in line:
                out.append(json.loads(line)["data"])
    return out


def _pct(x, nd=1):
    return "n/a" if x != x else f"{x * 100:.{nd}f}%"


def to_markdown(res: dict) -> str:
    s = res["summary"]
    L = [
        "# Meta-label experiment results (pre-registered)",
        "",
        f"Pre-registration: `{PREREG}`, SHA-256 `{res['prereg'][:16]}...` (matches the hash logged before the run).",
        f"{res['rows']} trend-entry samples ({res['start']} to {res['end']}), triple-barrier 4 sigma / 2 sigma / 20 days. "
        f"Taking every entry averages {res['mean_r']:+.3f} R at base costs and {res['mean_r_2x']:+.3f} R at 2x; {res['base_rate'] * 100:.0f}% end positive.",
        f"Deflated Sharpe counts {res['n_trials']} trials (the cumulative registry plus this experiment's four).",
        "",
        "| | Sharpe (mean, min to max) | at 2x costs | gain vs primary alone at 2x | CAGR | Max DD | Excess R per entry taken | Deflated Sharpe | Null p | Shows value? |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in s["models"]:
        c = r["criteria"]
        verdict = "**YES**" if r["shows_value"] else "no (" + ", ".join(k for k, v in c.items() if not v) + " failed)"
        L.append(f"| {r['name']} | {r['sharpe_mean']:.2f} ({r['sharpe_min']:.2f} to {r['sharpe_max']:.2f}) | {r['sharpe_2x_mean']:.2f} | "
                 f"{r['sharpe_gain_2x']:+.2f} | {_pct(r['cagr_mean'])} | {_pct(r['max_dd_mean'])} | {r['trade_score_mean']:+.3f} | "
                 f"{r['dsr_mean']:.2f} | {r['p_value']:.3f} ({r['n_null']} draws) | {verdict} |")
    for b in s["baselines"]:
        L.append(f"| baseline: {b['name']} | {b['sharpe']:.2f} | {b['sharpe_2x']:.2f} | n/a | {_pct(b['cagr'])} | {_pct(b['max_dd'])} | n/a | {b['dsr']:.2f} | n/a | n/a |")
    L += ["", f"Criteria (all required): Sharpe at 2x costs at least {MIN_SHARPE_GAIN:.2f} above the primary rule alone, shift-null p below {MAX_P}, Deflated Sharpe at least {MIN_DSR}.", ""]
    return "\n".join(L)
