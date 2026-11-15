import numpy as np
import pandas as pd

from getrich.eval import channel_ablation as ca
from getrich.news import study


def test_variants_depend_on_selection():
    assert list(ca.variants_for("chronos2", "gdelt")) == ["A", "B", "C", "D"]
    assert list(ca.variants_for(None, "gdelt")) == ["A", "C"]
    assert list(ca.variants_for("chronos2", None)) == ["A", "B"]
    assert list(ca.variants_for(None, None)) == ["A"]


def test_variants_only_add_channels_to_the_baseline():
    for key, (_name, ch) in ca.VARIANTS.items():
        assert ch[: len(ca.BASE_CHANNELS)] == ca.BASE_CHANNELS
    assert set(ca.VARIANTS["D"][1]) == set(ca.VARIANTS["B"][1]) | set(ca.VARIANTS["C"][1])


def test_worker_cmd_passes_selection(tmp_path):
    cmd = ca.worker_cmd("lgbm", tmp_path / "o.npz", 40, "chronos2", "gdelt", ca.VARIANTS["D"][1], tmp_path / "m.pkl")
    assert cmd[cmd.index("--foundation") + 1] == "chronos2" and cmd[cmd.index("--news") + 1] == "gdelt"
    assert cmd[cmd.index("--channels") + 1] == "market,forecast,context,foundation,news"
    assert "--save" in cmd and "--meta" in cmd
    bare = ca.worker_cmd("linear", tmp_path / "o.npz", 0, None, None, ca.BASE_CHANNELS)
    assert "--foundation" not in bare and "--news" not in bare and "--save" not in bare


def test_judge_needs_every_criterion_against_both_comparators():
    row = {"sharpe_2x_mean": 1.0, "dsr_mean": 0.95}
    ok = ca.judge(row, ref_2x=0.7, alone_2x=0.8, p_value=0.01)
    assert ok["shows_value"] and abs(ok["gain_vs_A_2x"] - 0.3) < 1e-9
    assert not ca.judge(row, ref_2x=0.7, alone_2x=0.95, p_value=0.01)["shows_value"]    # beats A but not primary alone
    assert not ca.judge(row, ref_2x=0.95, alone_2x=0.5, p_value=0.01)["shows_value"]    # beats primary alone but not A
    assert not ca.judge(row, ref_2x=0.7, alone_2x=0.5, p_value=0.2)["shows_value"]      # not distinguishable from the null
    assert not ca.judge({**row, "dsr_mean": 0.5}, 0.7, 0.5, 0.01)["shows_value"]        # not robust to the number of trials


def test_prereg_hash_logged_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("GETRICH_HOME", str(tmp_path))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "p.md").write_text("plan v1")
    from getrich import config

    monkeypatch.setattr(config, "root", lambda: tmp_path)
    monkeypatch.setattr(config, "logs_dir", lambda: tmp_path / "logs")
    (tmp_path / "logs").mkdir()
    emitted = []
    monkeypatch.setattr(ca, "emit", lambda name, **kw: (emitted.append((name, kw)), (tmp_path / "logs" / "events-x.jsonl").open("a").write(
        '{"data": {"sha256": "%s"}, "name": "eval.preregistered"}\n' % kw["sha256"])))
    h1 = ca.register_prereg("docs/p.md")
    assert ca.register_prereg("docs/p.md") == h1 and len(emitted) == 1     # second call does not log again
    (tmp_path / "docs" / "p.md").write_text("plan v2")
    assert ca.prereg_hash("docs/p.md") != h1                              # an edit no longer matches the logged hash
    assert ca.prereg_hash("docs/p.md") not in {e["sha256"] for e in ca.prereg_events()}


def test_event_study_finds_planted_signal_and_not_noise():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2021-01-01", periods=900, freq="D", tz="UTC")
    ret = rng.normal(0, 0.02, len(idx))
    close = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx)
    signal = pd.Series(np.r_[ret[1:], 0] * 5 + rng.normal(0, 0.02, len(idx)), index=idx)   # leaks the NEXT day's return: planted
    noise = pd.Series(rng.normal(size=len(idx)), index=idx)
    rows = study.study_frame(pd.DataFrame({"planted": signal, "noise": noise}), close, 1, "T", reps=100)
    by = {r["feature"]: r for r in rows}
    assert by["planted"]["significant"] and by["planted"]["ic"] > 0.3
    assert not by["noise"]["significant"]


def test_event_study_forward_returns_look_forward():
    close = pd.Series([100.0, 110.0, 121.0, 133.1])
    r = study.forward_log_returns(close, 1)
    assert abs(r.iloc[0] - np.log(1.1)) < 1e-12 and np.isnan(r.iloc[-1])


def test_event_study_constant_feature_is_skipped_not_crashed():
    idx = pd.date_range("2021-01-01", periods=200, freq="D", tz="UTC")
    close = pd.Series(np.linspace(100, 200, 200), index=idx)
    rows = study.study_frame(pd.DataFrame({"flat": np.zeros(200)}, index=idx), close, 5, "T", reps=20)
    assert rows[0]["ic"] != rows[0]["ic"] and not rows[0]["significant"]


def test_save_final_roundtrip(tmp_path):
    import pickle

    from getrich.eval import pinet_worker as w

    ds = w.synthetic_dataset(0.5, seed=1, n=600)
    path = tmp_path / "m.pkl"
    w.save_final("linear", ds, str(path), {"foundation": None, "news": None})
    blob = pickle.loads(path.read_bytes())
    assert blob["meta"]["columns"] == ds.columns and blob["meta"]["rows"] == 600
    assert blob["meta"]["from"] <= blob["meta"]["to"]
    pred = blob["model"].predict(ds.X)
    assert pred.shape == (600, 2) and np.isfinite(pred).all()
