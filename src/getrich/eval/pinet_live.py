"""The live PI-Net: a frozen model scores today's trade candidate for BTC and ETH, every score goes into the hash-chained ledger the day it is made,
and each is resolved later against the daily bars that follow. This is the pre-registered forward study (docs/preregistration-pinet-forward.md).

It changes no trading behaviour. The model has no demonstrated edge (docs/news-forecast-results.md); this only builds an honest out-of-sample record.
Nothing is backfilled, nothing is refitted, and the code refuses to run unless the registered pre-registration hash is logged and the model file is
byte-identical to the one pinned in that document.

Pure numpy, pandas and the store at import time; the LightGBM model is only loaded inside `predict_all` (the models container has it).
"""

from __future__ import annotations

import hashlib
import json
import math
import pickle
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config
from ..ids import new_id
from ..obs.events import emit, utcnow
from ..store.db import connect
from ..store.ledger import record_insight
from . import features, labels
from .costs import CostModel
from .data import load_bars
from .labels import EPS

SERVICE = "eval.pinet_live"
MODEL_FILE = "pinet-lgbm-chronos2-nonews.pkl"
PINNED_SHA256 = "3fcca104e7a75724bea3c9ee91e54adcee7c8ec361a9d845c28ab3b7a030762a"
PREREG = "docs/preregistration-pinet-forward.md"
FOUNDATION = "chronos2"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
TP_MULT, SL_MULT, HORIZON, MIN_VOTES = 4.0, 2.0, 20, 2 / 3          # the research's META_KWARGS (a test keeps them equal)
BLOCK_DAYS, DRAWS, SEED = 20, 10_000, 20261116
MIN_DELTA, ALPHA, MIN_TAKE = 0.10, 0.05, 40
CHECK_DAYS, CHECK_RESOLVED = 180, 150
KIND = "pinet_prediction"


# ------------------------------------------------------------------------------------------------ guards

def model_path() -> Path:
    return config.data_dir() / "models" / "pinet" / MODEL_FILE


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prereg_sha() -> str:
    return hashlib.sha256(Path(config.root(), PREREG).read_bytes()).hexdigest()


def prereg_logged() -> bool:
    """The pre-registration's current hash must appear as a logged `eval.preregistered` event (see `getrich preregister`)."""
    want = prereg_sha()
    for p in sorted(config.logs_dir().glob("events-*.jsonl")):
        for line in p.read_text().splitlines():
            if '"eval.preregistered"' in line and want in line:
                return True
    return False


def load_model():
    path = model_path()
    if not path.exists():
        raise RuntimeError(f"the pinned PI-Net model is not at {path}")
    if file_sha256(path) != PINNED_SHA256:
        raise RuntimeError("the PI-Net model file does not match the hash pinned in the pre-registration; it must not be used or replaced inside the study")
    with open(path, "rb") as f:
        d = pickle.load(f)
    return d["model"], d["meta"]


# ------------------------------------------------------------------------------------------------ the decision row

def decision_row(symbol: str, daily: pd.DataFrame, hourly: pd.DataFrame, columns: list[str]) -> dict:
    """Inputs for the newest closed daily bar, built by the same code that built the training rows. Returns {"status": ...} when it cannot be made yet."""
    last = daily.index[-1]
    if hourly.index.max() < last + pd.Timedelta(hours=23):                # the HAR volatility needs the whole day's hourly bars
        return {"status": "waiting_for_hourly_bars"}
    feats = features.feature_frame(symbol, daily, hourly)
    try:
        fnd = features.foundation_frame(symbol, daily, [FOUNDATION])
    except RuntimeError:
        return {"status": "no_forecast_cache"}
    if last not in fnd.index:
        return {"status": "waiting_for_the_forecast"}
    row = pd.concat([feats.loc[last], fnd.loc[last]])
    bad = [c for c in columns if c not in row.index or not np.isfinite(row[c])]
    if bad:
        return {"status": "incomplete_inputs", "missing": bad[:6]}
    sigma = float(labels.daily_vol(daily["close"]).loc[last])
    if not np.isfinite(sigma) or sigma <= 0:
        return {"status": "no_volatility"}
    return {"status": "ready", "bar": last, "row": row[columns], "sigma": sigma, "entry": float(daily["close"].iloc[-1]), "trend_votes": float(row["trend_votes"])}


def call_for(trend_votes: float, expected_r: float | None) -> str:
    if trend_votes < MIN_VOTES - 1e-9:
        return "out_of_domain"
    return "take" if expected_r is not None and expected_r > 0 else "skip"


# ------------------------------------------------------------------------------------------------ resolving a decision (mirrors labels.triple_barrier)

def resolve(entry: float, stop_frac: float, tp_frac: float, horizon: int, after: pd.DataFrame, cost: CostModel | None = None) -> dict | None:
    """The outcome of a long entered at `entry`, against the closed daily bars after the decision bar. None while it is still open. Same rules as
    labels.triple_barrier: the stop is checked before the take profit on a bar, barriers fill at their price, the timeout is the close of bar `horizon`."""
    cost = cost or CostModel()
    sl_px, tp_px = entry * (1 - stop_frac), entry * (1 + tp_frac)
    hi, lo, cl = after["high"].to_numpy(), after["low"].to_numpy(), after["close"].to_numpy()
    for k in range(1, min(len(after), horizon) + 1):
        kind = px = None
        if lo[k - 1] <= sl_px * (1 + EPS):
            kind, px = "sl", sl_px
        elif hi[k - 1] >= tp_px * (1 - EPS):
            kind, px = "tp", tp_px
        elif k == horizon:
            kind, px = "timeout", float(cl[k - 1])
        if kind:
            r_gross = (px / entry - 1.0) / stop_frac
            return {"exit": kind, "bars_held": k, "r_gross": r_gross, "r_net": r_gross - cost.cost_in_r(stop_frac),
                    "r_net_2x": r_gross - cost.stressed(2.0).cost_in_r(stop_frac), "exit_bar": f"{after.index[k - 1]:%Y-%m-%d}"}
    return None


# ------------------------------------------------------------------------------------------------ recording

def _already(con, symbol: str, bar: str) -> bool:
    return con.execute("SELECT 1 FROM insights WHERE asset = ? AND json_extract_string(payload, '$.kind') = ? AND json_extract_string(payload, '$.decision_bar') = ? "
                       "AND json_extract_string(payload, '$.model_sha256') = ? LIMIT 1", [symbol, KIND, bar, PINNED_SHA256]).fetchone() is not None


def _store_inputs(con, symbol: str, bar: str, row: pd.Series, now) -> str:
    text = json.dumps({"symbol": symbol, "decision_bar": bar, "model_sha256": PINNED_SHA256, "features": {k: float(v) for k, v in row.items()}}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode()).hexdigest()
    got = con.execute("SELECT item_id FROM news_items WHERE content_hash = ?", [digest]).fetchone()
    if got:
        return got[0]
    item_id = new_id("n")
    con.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?)", [item_id, "pinet_inputs", "pinet://inputs", f"PI-Net inputs {symbol} {bar}", text, None, now, digest])
    con.execute("INSERT OR REPLACE INTO item_processing VALUES (?,?,?,?)", [item_id, "pinet_inputs", "pinet_live", now])
    return item_id


def predict_all(symbols: tuple[str, ...] = SYMBOLS, model=None, meta=None, now=None) -> list[dict]:
    """Score the newest closed daily bar for each symbol and write it to the ledger (once per symbol and bar)."""
    if not prereg_logged():
        raise RuntimeError(f"the pre-registration is not logged: run `getrich preregister {PREREG}` first")
    if model is None:
        model, meta = load_model()
    cols, now, psha = list(meta["columns"]), now or utcnow(), prereg_sha()
    results = []
    data = {s: (load_bars(s, "1d"), load_bars(s, "1h")) for s in symbols}          # read with no lock held while the model runs
    for sym, (daily, hourly) in data.items():
        bar = f"{daily.index[-1]:%Y-%m-%d}"
        with connect() as con:
            if _already(con, sym, bar):
                results.append({"symbol": sym, "bar": bar, "status": "already_recorded"})
                continue
        d = decision_row(sym, daily, hourly, cols)
        if d["status"] != "ready":
            results.append({"symbol": sym, "bar": bar, "status": d["status"]})
            continue
        in_domain = d["trend_votes"] >= MIN_VOTES - 1e-9
        p = e = None
        if in_domain:
            out = np.asarray(model.predict(d["row"].to_numpy(dtype=np.float32)[None, :]))
            p, e = float(out[0, 0]), float(out[0, 1])
        call = call_for(d["trend_votes"], e)
        payload = {"kind": KIND, "source": "pinet_live", "symbol": sym, "decision_bar": bar, "in_domain": in_domain, "trend_votes": round(d["trend_votes"], 4),
                   "p_positive": p, "expected_r": e, "call": call, "entry": d["entry"], "sigma": d["sigma"], "stop_frac": SL_MULT * d["sigma"], "tp_frac": TP_MULT * d["sigma"],
                   "horizon_days": HORIZON, "model_sha256": PINNED_SHA256, "prereg": psha, "trained_through": str(meta.get("to"))}
        with connect() as con:
            ev = _store_inputs(con, sym, bar, d["row"], now)
            iid = record_insight(con, asset=sym, evidence=[ev], model="pinet-lgbm-chronos2", as_of=now, payload=payload)
        results.append({"symbol": sym, "bar": bar, "status": "recorded", "call": call, "p": p, "e": e, "insight_id": iid})
    emit("pinet.live_run", service=SERVICE, recorded=sum(r["status"] == "recorded" for r in results), waiting=sum(r["status"] not in ("recorded", "already_recorded") for r in results))
    return results


def score(now=None) -> dict:
    """Resolve open in-domain decisions against the daily bars that came after them."""
    now = now or utcnow()
    with connect() as con:
        rows = con.execute("SELECT i.insight_id, i.asset, i.payload FROM insights i LEFT JOIN insight_outcomes o ON o.insight_id = i.insight_id "
                           "WHERE o.insight_id IS NULL AND json_extract_string(i.payload, '$.kind') = ? AND json_extract_string(i.payload, '$.in_domain') = 'true' ORDER BY i.seq", [KIND]).fetchall()
    out, daily, done = {"resolved": 0, "pending": 0}, {}, []
    for iid, sym, payload in rows:
        p = json.loads(payload)
        if sym not in daily:
            daily[sym] = load_bars(sym, "1d")
        after = daily[sym][daily[sym].index > pd.Timestamp(p["decision_bar"], tz="UTC")]
        res = resolve(p["entry"], p["stop_frac"], p["tp_frac"], int(p["horizon_days"]), after)
        if res is None:
            out["pending"] += 1
            continue
        done.append((iid, now, int(p["horizon_days"]), res["r_net"], bool(res["r_net"] > 0), json.dumps({**res, "call": p["call"], "decision_bar": p["decision_bar"]})))
        out["resolved"] += 1
    if done:
        with connect() as con:
            con.executemany("INSERT INTO insight_outcomes VALUES (?,?,?,?,?,?)", done)
    emit("pinet.score_run", service=SERVICE, **out)
    return out


def run(now=None) -> dict:
    results = predict_all(now=now)
    return {"predictions": results, "scored": score(now)}


# ------------------------------------------------------------------------------------------------ reading the record

def records(con=None) -> list[dict]:
    """Every in-domain decision of the registered study, resolved or not."""
    def q(c):
        return c.execute("SELECT i.as_of, i.payload, o.detail FROM insights i LEFT JOIN insight_outcomes o ON o.insight_id = i.insight_id "
                         "WHERE json_extract_string(i.payload, '$.kind') = ? AND json_extract_string(i.payload, '$.in_domain') = 'true' ORDER BY i.seq", [KIND]).fetchall()
    rows = q(con) if con is not None else _with(q)
    out = []
    for _as_of, payload, detail in rows:
        p, d = json.loads(payload), (json.loads(detail) if detail else None)
        out.append({"date": p["decision_bar"], "symbol": p["symbol"], "call": p["call"], "p": p["p_positive"], "e": p["expected_r"], "r": d["r_net"] if d else None, "r2": d["r_net_2x"] if d else None,
                    "exit": d["exit"] if d else None})
    return out


def _with(fn):
    with connect() as con:
        return fn(con)


def latest() -> dict:
    """The newest recorded call per symbol (any call, including out-of-domain days), for the screens and the trader's packet."""
    def q(con):
        out = {}
        for sym in SYMBOLS:
            r = con.execute("SELECT payload FROM insights WHERE asset = ? AND json_extract_string(payload, '$.kind') = ? ORDER BY seq DESC LIMIT 1", [sym, KIND]).fetchone()
            if r:
                p = json.loads(r[0])
                out[sym] = {k: p[k] for k in ("decision_bar", "call", "trend_votes", "p_positive", "expected_r")}
        return out
    return _with(q)


def summarize(recs: list[dict]) -> dict:
    done = [r for r in recs if r["r"] is not None]
    take = [r for r in done if r["call"] == "take"]
    skip = [r for r in done if r["call"] == "skip"]
    m = lambda xs, k="r": float(np.mean([x[k] for x in xs])) if xs else None
    return {"decisions": len(recs), "resolved": len(done), "pending": len(recs) - len(done), "take": len(take), "skip": len(skip), "mean_all": m(done), "mean_take": m(take),
            "mean_skip": m(skip), "mean_take_2x": m(take, "r2"), "delta": (m(take) - m(done)) if take else None}


def block_p(recs: list[dict], draws: int = DRAWS, seed: int = SEED) -> float | None:
    """One-sided moving-block bootstrap p for 'take beats all': the share of draws where mean(take) - mean(all) <= 0. Blocks are BLOCK_DAYS calendar days;
    every decision in a block (both coins) is resampled together. A draw with no take decision counts as no improvement."""
    done = [r for r in recs if r["r"] is not None]
    if not done or not any(r["call"] == "take" for r in done):
        return None
    t0 = min(pd.Timestamp(r["date"]) for r in done)
    blocks: dict[int, list[dict]] = {}
    for r in done:
        blocks.setdefault((pd.Timestamp(r["date"]) - t0).days // BLOCK_DAYS, []).append(r)
    keys = sorted(blocks)
    s_all = np.array([sum(x["r"] for x in blocks[k]) for k in keys])
    n_all = np.array([len(blocks[k]) for k in keys], dtype=float)
    s_take = np.array([sum(x["r"] for x in blocks[k] if x["call"] == "take") for k in keys])
    n_take = np.array([sum(1 for x in blocks[k] if x["call"] == "take") for k in keys], dtype=float)
    idx = np.random.default_rng(seed).integers(0, len(keys), size=(draws, len(keys)))
    sa, na, st, nt = s_all[idx].sum(1), n_all[idx].sum(1), s_take[idx].sum(1), n_take[idx].sum(1)
    diff = np.where(nt > 0, st / np.maximum(nt, 1) - sa / np.maximum(na, 1), 0.0)
    return float((diff <= 0).mean())


def verdict(recs: list[dict], today=None) -> dict:
    """The pre-registered checkpoint. `due` only after CHECK_DAYS days since the first decision and CHECK_RESOLVED resolved decisions."""
    s = summarize(recs)
    t = pd.Timestamp(today if today is not None else utcnow())
    today = t.tz_convert("UTC").tz_localize(None) if t.tzinfo is not None else t
    first = min((pd.Timestamp(r["date"]) for r in recs), default=None)
    days = None if first is None else int((today.normalize() - first).days)
    due = days is not None and days >= CHECK_DAYS and s["resolved"] >= CHECK_RESOLVED
    p = block_p(recs)
    checks = {
        "difference_at_least_0.10R": s["delta"] is not None and s["delta"] >= MIN_DELTA,
        "block_bootstrap_p_below_0.05": p is not None and p < ALPHA,
        "take_positive_at_2x_costs": s["mean_take_2x"] is not None and s["mean_take_2x"] > 0,
        "at_least_40_take_resolved": s["take"] >= MIN_TAKE,
        "model_file_unchanged": model_path().exists() and file_sha256(model_path()) == PINNED_SHA256,
    }
    return {"due": due, "days_since_first": days, "summary": s, "p": p, "checks": checks, "shows_value": bool(due and all(checks.values())),
            "left": None if first is None else {"days": max(CHECK_DAYS - (days or 0), 0), "resolved": max(CHECK_RESOLVED - s["resolved"], 0)}}


def daily_sharpe_annual(recs: list[dict]) -> float | None:
    """The crude number the study adds to the trial registry: annualised Sharpe of the daily mean net R of the take decisions."""
    by: dict[str, list[float]] = {}
    for r in recs:
        if r["call"] == "take" and r["r"] is not None:
            by.setdefault(r["date"], []).append(r["r"])
    xs = np.array([np.mean(v) for v in by.values()])
    if len(xs) < 3 or xs.std(ddof=1) == 0:
        return None
    return float(xs.mean() / xs.std(ddof=1) * math.sqrt(365))
