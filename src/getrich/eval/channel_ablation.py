"""Channel ablation for the PI-Net: does a pretrained forecaster and/or a news stream add anything to the market features?

Four variants are built from ONE dataset (same rows, labels and folds) by choosing which channels each model may see:
    A  baseline          market + forecast (HAR) + context
    B  + foundation      A plus the pretrained forecaster's features
    C  + news            A plus the GDELT news features
    D  + both            A plus foundation plus news
Each variant is one model-per-process worker run (PyTorch and LightGBM cannot share a process on macOS), and every
variant is judged against (1) the same model on variant A and (2) taking every trend entry. Criteria are fixed in the
pre-registration; this module tunes nothing. Variants are trials in the cumulative registry, so the Deflated Sharpe
counts them.

`train()` is the exploratory path (select a forecaster, train, optionally save a final fit). It is labelled
exploratory and does not register trials.
"""

from __future__ import annotations

import hashlib
import json
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
BASE_CHANNELS = ("market", "forecast", "context")
VARIANTS = {
    "A": ("baseline", BASE_CHANNELS),
    "B": ("+foundation", BASE_CHANNELS + ("foundation",)),
    "C": ("+news", BASE_CHANNELS + ("news",)),
    "D": ("+foundation+news", BASE_CHANNELS + ("foundation", "news")),
}
MIN_SHARPE_GAIN = 0.10      # criterion 1, at 2x costs, versus the same model on variant A and versus primary alone
MAX_P = 0.05                # criterion 2, shift-null p of the variant itself
MIN_DSR = 0.90              # criterion 3
PREREG = "docs/preregistration-news-forecast.md"
DEFAULT_NULLS = {"linear": 100, "lgbm": 40, "fusion": 20}


def worker_cmd(model: str, out: Path, n_null: int, foundation: str | None, news: str | None, channels: tuple[str, ...],
               save: Path | None = None) -> list[str]:
    cmd = [sys.executable, "-I", "-m", "getrich.eval.pinet_worker", "--model", model, "--meta", "--out", str(out), "--null", str(n_null),
           "--channels", ",".join(channels)]
    if foundation:
        cmd += ["--foundation", foundation]
    if news:
        cmd += ["--news", news]
    if save:
        cmd += ["--save", str(save)]
    return cmd


def _run_worker(cmd: list[str], label: str) -> None:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    sys.stderr.write(proc.stderr[-300:])
    if proc.returncode != 0:
        raise RuntimeError(f"worker {label} failed:\n{proc.stderr[-1500:]}")


def variants_for(foundation: str | None, news: str | None) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Variants that can exist given what was selected; A always does."""
    out = {}
    for k, (name, ch) in VARIANTS.items():
        if "foundation" in ch and not foundation:
            continue
        if "news" in ch and not news:
            continue
        out[k] = (name, ch)
    return out


def prereg_events() -> list[dict]:
    out = []
    for p in sorted(config.logs_dir().glob("events-*.jsonl")):
        for line in p.read_text().splitlines():
            if '"eval.preregistered"' in line:
                out.append(json.loads(line)["data"])
    return out


def prereg_hash(path: str = PREREG) -> str:
    return hashlib.sha256(Path(config.root(), path).read_bytes()).hexdigest()


def register_prereg(path: str = PREREG) -> str:
    """Log the file's hash as an event so any later edit shows up as a mismatch. Idempotent."""
    h = prereg_hash(path)
    if h not in {e.get("sha256") for e in prereg_events()}:
        emit("eval.preregistered", service="eval", file=path, sha256=h)
    return h


def judge(row: dict, ref_2x: float, alone_2x: float, p_value: float) -> dict:
    """Criteria against both comparators. A variant 'shows value' only if every criterion holds against both."""
    gain_ref = row["sharpe_2x_mean"] - ref_2x
    gain_alone = row["sharpe_2x_mean"] - alone_2x
    crit = {"gain_vs_baseline_variant": gain_ref >= MIN_SHARPE_GAIN, "gain_vs_primary_alone": gain_alone >= MIN_SHARPE_GAIN,
            "p_value": p_value < MAX_P, "dsr": row["dsr_mean"] >= MIN_DSR}
    return {"gain_vs_A_2x": gain_ref, "gain_vs_alone_2x": gain_alone, "criteria": crit, "shows_value": all(crit.values())}


def run(foundation: str = "chronos2", news: str = "gdelt", models: tuple[str, ...] = MODELS, null_counts: dict[str, int] | None = None,
        cost: CostModel | None = None, register: bool = True, require_prereg: bool = True) -> dict:
    cost = cost or CostModel()
    null_counts = null_counts or DEFAULT_NULLS
    h = prereg_hash() if require_prereg else None
    if require_prereg and h not in {e.get("sha256") for e in prereg_events()}:
        raise RuntimeError("the pre-registration file does not match any logged hash: run `getrich preregister` first, and do not edit it afterwards")
    variants = variants_for(foundation, news)

    ds = make_dataset(cost=cost, foundation_models=[foundation] if foundation else None, news=news, **META_KWARGS)
    closes = {s: load_bars(s, "1d")["close"] for s in sorted(set(ds.asset))}
    results, extras = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for model in models:
            for key, (vname, channels) in variants.items():
                out = Path(tmp) / f"{model}-{key}.npz"
                _run_worker(worker_cmd(model, out, null_counts.get(model, 0), foundation, news, channels), f"{model}:{key}")
                z = np.load(out, allow_pickle=True)
                if not np.array_equal(z["t0"], ds.t0.astype("int64")) or not np.array_equal(z["asset"], ds.asset):
                    raise RuntimeError(f"{model}:{key}: worker row order differs from the parent dataset")
                name = f"{model}:{key}"
                results.append(pinet_eval.evaluate_model(name, list(z["preds"]), ds, closes, cost))
                extras[name] = {"p_value": float(z["p_value"]), "n_null": int(len(z["null_scores"])), "variant": vname, "channels": list(channels)}

    take_all = np.ones((len(ds), 2))
    stressed = cost.stressed(2.0)
    base = pinet_eval.baseline_returns(ds, closes, cost)
    base["primary_alone"] = pinet_eval.model_returns(ds, take_all, closes, cost)
    base_2x = pinet_eval.baseline_returns(ds, closes, stressed)
    base_2x["primary_alone"] = pinet_eval.model_returns(ds, take_all, closes, stressed)

    new_period = [float(np.mean([p["sharpe_period"] for p in r["paths"]])) for r in results]
    new_period.append(float(base["primary_alone"].mean() / base["primary_alone"].std(ddof=1)))
    all_trials = trials.period_sharpes() + new_period
    summary = pinet_eval.summarize(results, base, base_2x, trial_sharpes=all_trials)
    alone_2x = next(b for b in summary["baselines"] if b["name"] == "primary_alone")["sharpe_2x"]
    by_name = {r["name"]: r for r in summary["models"]}
    for row in summary["models"]:
        row.update(extras[row["name"]])
        model, key = row["name"].split(":")
        ref = by_name[f"{model}:A"]["sharpe_2x_mean"]
        row.update(judge(row, ref, alone_2x, row["p_value"]))
        if key == "A":
            row["shows_value"] = None       # the reference is not a claim
    if register:
        for r in summary["models"]:
            trials.register(3, f"news-forecast-v1:{r['name']}", r["sharpe_mean"], "docs/news-forecast-results.md")
    emit("eval.news_forecast_run", service="eval", prereg_sha256=h, foundation=foundation, news=news, n_trials=len(all_trials),
         shows_value={r["name"]: r["shows_value"] for r in summary["models"]})
    return {"summary": summary, "rows": len(ds), "n_trials": len(all_trials), "prereg": h, "cost": cost, "foundation": foundation, "news": news,
            "base_rate": float(ds.y.mean()), "mean_r": float(ds.r_net.mean()), "mean_r_2x": float(ds.r_at(2.0).mean()),
            "start": str(ds.bar.min().date()), "end": str(ds.bar.max().date()),
            "assets": {s: int((ds.asset == s).sum()) for s in sorted(set(ds.asset))}}


def train(foundation: str | None, news: str | None, models: tuple[str, ...] = ("lgbm",), save_dir: Path | None = None,
          null_count: int = 0, cost: CostModel | None = None) -> dict:
    """Exploratory: baseline (A) versus the selected channel set, on identical rows. Not registered, not a claim.
    With `save_dir`, also fits and pickles the selected-channel model on all rows."""
    cost = cost or CostModel()
    selected = BASE_CHANNELS + (("foundation",) if foundation else ()) + (("news",) if news else ())
    ds = make_dataset(cost=cost, foundation_models=[foundation] if foundation else None, news=news, **META_KWARGS)
    closes = {s: load_bars(s, "1d")["close"] for s in sorted(set(ds.asset))}
    runs = [("A", BASE_CHANNELS)] + ([("selected", selected)] if selected != BASE_CHANNELS else [])
    results, saved = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for model in models:
            for key, channels in runs:
                out = Path(tmp) / f"{model}-{key}.npz"
                save = None
                if save_dir and key == "selected":
                    save_dir.mkdir(parents=True, exist_ok=True)
                    save = save_dir / f"pinet-{model}-{foundation or 'nofm'}-{news or 'nonews'}.pkl"
                    saved[model] = str(save)
                _run_worker(worker_cmd(model, out, null_count, foundation, news, channels, save), f"{model}:{key}")
                z = np.load(out, allow_pickle=True)
                results.append(pinet_eval.evaluate_model(f"{model}:{key}", list(z["preds"]), ds, closes, cost))
    take_all = np.ones((len(ds), 2))
    base = pinet_eval.baseline_returns(ds, closes, cost)
    base["primary_alone"] = pinet_eval.model_returns(ds, take_all, closes, cost)
    base_2x = pinet_eval.baseline_returns(ds, closes, cost.stressed(2.0))
    base_2x["primary_alone"] = pinet_eval.model_returns(ds, take_all, closes, cost.stressed(2.0))
    new_period = [float(np.mean([p["sharpe_period"] for p in r["paths"]])) for r in results]
    new_period.append(float(base["primary_alone"].mean() / base["primary_alone"].std(ddof=1)))
    summary = pinet_eval.summarize(results, base, base_2x, trial_sharpes=trials.period_sharpes() + new_period)
    return {"summary": summary, "rows": len(ds), "selected": list(selected), "saved": saved, "foundation": foundation, "news": news,
            "start": str(ds.bar.min().date()), "end": str(ds.bar.max().date())}


def _pct(x, nd=1):
    return "n/a" if x != x else f"{x * 100:.{nd}f}%"


def train_markdown(res: dict) -> str:
    s = res["summary"]
    L = [f"Exploratory run (not pre-registered, not counted as trials): forecaster={res['foundation'] or 'none'}, news={res['news'] or 'none'}, "
         f"{res['rows']} rows {res['start']} to {res['end']}.", f"Selected channels: {', '.join(res['selected'])}.", "",
         "| | Sharpe | at 2x costs | CAGR | Max DD | Excess R per entry |", "|---|---:|---:|---:|---:|---:|"]
    for r in s["models"]:
        L.append(f"| {r['name']} | {r['sharpe_mean']:.2f} | {r['sharpe_2x_mean']:.2f} | {_pct(r['cagr_mean'])} | {_pct(r['max_dd_mean'])} | {r['trade_score_mean']:+.3f} |")
    for b in s["baselines"]:
        L.append(f"| baseline: {b['name']} | {b['sharpe']:.2f} | {b['sharpe_2x']:.2f} | {_pct(b['cagr'])} | {_pct(b['max_dd'])} | n/a |")
    if res["saved"]:
        L += ["", "Saved final fits (all rows, deployable; the honest estimate is the cross-validated row above):"] + [f"- {m}: `{p}`" for m, p in res["saved"].items()]
    return "\n".join(L)


def to_markdown(res: dict) -> str:
    s = res["summary"]
    L = [
        "# News + forecaster experiment results (pre-registered)",
        "",
        f"Pre-registration: `{PREREG}`, SHA-256 `{res['prereg'][:16]}...` (matches the hash logged before the run).",
        f"Forecaster channel: {res['foundation']}. News channel: {res['news']}. {res['rows']} trend-entry samples ({res['start']} to {res['end']}); "
        f"per asset {res['assets']}. Triple-barrier 4 sigma / 2 sigma / 20 days. Taking every entry averages {res['mean_r']:+.3f} R at base costs "
        f"and {res['mean_r_2x']:+.3f} R at 2x; {res['base_rate'] * 100:.0f}% end positive.",
        f"Deflated Sharpe counts {res['n_trials']} trials (the cumulative registry plus this experiment's).",
        "",
        "| | channels | Sharpe (mean, min to max) | at 2x costs | gain vs A at 2x | gain vs primary alone at 2x | CAGR | Max DD | Excess R per entry | Deflated Sharpe | Null p | Shows value? |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in s["models"]:
        c = r["criteria"]
        if r["shows_value"] is None:
            verdict = "reference"
        elif r["shows_value"]:
            verdict = "**YES**"
        else:
            verdict = "no (" + ", ".join(k for k, v in c.items() if not v) + " failed)"
        L.append(f"| {r['name']} | {r['variant']} | {r['sharpe_mean']:.2f} ({r['sharpe_min']:.2f} to {r['sharpe_max']:.2f}) | {r['sharpe_2x_mean']:.2f} | "
                 f"{r['gain_vs_A_2x']:+.2f} | {r['gain_vs_alone_2x']:+.2f} | {_pct(r['cagr_mean'])} | {_pct(r['max_dd_mean'])} | "
                 f"{r['trade_score_mean']:+.3f} | {r['dsr_mean']:.2f} | {r['p_value']:.3f} ({r['n_null']} draws) | {verdict} |")
    for b in s["baselines"]:
        L.append(f"| baseline: {b['name']} | | {b['sharpe']:.2f} | {b['sharpe_2x']:.2f} | n/a | n/a | {_pct(b['cagr'])} | {_pct(b['max_dd'])} | n/a | {b['dsr']:.2f} | n/a | n/a |")
    L += ["", f"Criteria (all required, for each of B, C, D): Sharpe at 2x costs at least {MIN_SHARPE_GAIN:.2f} above BOTH the same model on A and the primary rule alone, "
          f"shift-null p below {MAX_P}, Deflated Sharpe at least {MIN_DSR}.", ""]
    return "\n".join(L)
