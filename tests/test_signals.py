import pytest

from getrich.agents import signals as sg, trader


def row(**over):
    base = {"class": "crypto", "trend_votes_of_3": 3.0, "ret_7d": 0.08, "vol_20d_annual": 0.5, "range_position_7d": 0.9, "z_vs_48h_mean": 0.2, "hourly_trend_up": True}
    base.update(over)
    return base


def test_an_all_bullish_row_is_a_buy_zone_and_an_all_bearish_one_is_avoid():
    up = sg.board(row())
    assert up["zone"] == "buy" and up["score"] >= sg.BUY_ZONE and up["up"] >= 4 and up["down"] == 0
    down = sg.board(row(trend_votes_of_3=0.0, ret_7d=-0.15, range_position_7d=0.05, hourly_trend_up=False, z_vs_48h_mean=1.0))
    assert down["zone"] == "avoid" and down["score"] <= sg.AVOID_ZONE and down["down"] >= 4


def test_mixed_indicators_say_wait_and_the_score_is_the_plain_average_of_the_votes_that_exist():
    b = sg.board(row(trend_votes_of_3=0.0, hourly_trend_up=True, ret_7d=-0.05, range_position_7d=0.5, z_vs_48h_mean=0.0))
    vals = [v["value"] for v in b["votes"] if v["value"] is not None]
    assert b["zone"] == "wait" and b["score"] == pytest.approx(sum(vals) / len(vals), abs=0.01)


def test_every_vote_carries_what_our_tests_found_and_none_beyond_the_daily_trend_has_earned_trust():
    b = sg.board(row(), {"forecast_prob_up_5d": 0.6, "pinet_call": "take", "news_tilt": 0.5})
    proofs = {v["id"]: v["proof"] for v in b["votes"]}
    assert proofs["daily_trend"] == "weak" and all(p == "none" for k, p in proofs.items() if k != "daily_trend")
    assert {"forecasts", "pinet", "news"} <= set(proofs)


def test_out_of_domain_pinet_and_a_missing_forecast_are_not_counted_as_opinions():
    b = sg.board(row(), {"pinet_call": "out_of_domain"})
    pn = next(v for v in b["votes"] if v["id"] == "pinet")
    assert pn["value"] is None and b["n"] == len([v for v in b["votes"] if v["value"] is not None])
    assert "forecasts" not in {v["id"] for v in sg.board(row())["votes"]}


def test_too_few_votes_is_no_read_rather_than_a_guess():
    b = sg.board({"class": "fx", "trend_votes_of_3": 2.0})
    assert b["zone"] == "no_read" and b["score"] is None


def test_a_skip_from_the_pinet_is_bearish_and_the_forecast_vote_follows_the_probability():
    assert next(v for v in sg.votes(row(), {"pinet_call": "skip"}) if v["id"] == "pinet")["value"] == -1.0
    lo = next(v for v in sg.votes(row(), {"forecast_prob_up_5d": 0.3}) if v["id"] == "forecasts")["value"]
    hi = next(v for v in sg.votes(row(), {"forecast_prob_up_5d": 0.7}) if v["id"] == "forecasts")["value"]
    assert lo < 0 < hi


def test_news_tilt_counts_only_events_that_name_the_coin_or_the_whole_market_and_nets_risk_on_against_risk_off():
    ev = [{"assets": ["BTC", "CRYPTO_MARKET"], "direction": "risk_off", "magnitude": "high", "confidence": 0.9},
          {"assets": ["ETH"], "direction": "risk_on", "magnitude": "high", "confidence": 0.9},
          {"assets": ["BTC"], "direction": "unclear", "magnitude": "high", "confidence": 0.9}]
    assert sg.news_tilt(ev, "BTCUSDT") < 0                                   # the ETH story does not count for BTC; the unclear one has no direction
    assert sg.news_tilt(ev, "SOLUSDT") < 0                                   # but the market-wide one reaches every coin
    assert sg.news_tilt([ev[1]], "BTCUSDT") is None


# ------------------------------------------------------------------ plan triggers


def packet(price=100.0):
    return {"universe": {"instruments": {"BTCUSDT": {"available": True, "price": price}, "ETHUSDT": {"available": False}}}}


def trig(**over):
    t = {"instrument": "BTCUSDT", "direction": "above", "level": 105.0, "basis": "daily_close", "meaning": "buy_candidate", "note": "prior-day high"}
    t.update(over)
    return t


def plan_with(triggers):
    import test_trader as tt

    return tt.plan(triggers=triggers)


def test_valid_triggers_pass_validation_and_bad_ones_are_named():
    assert trader.validate_plan(plan_with([trig(), trig(direction="below", level=95.0, meaning="stay_out")]), set(), ["BTCUSDT"]) == []
    for bad, frag in [(trig(level=-1), "level"), (trig(basis="whenever"), "not allowed"), (trig(note=""), "note"), (trig(instrument="XYZ"), "not allowed"), (trig(meaning="moon"), "not allowed")]:
        errs = trader.validate_plan(plan_with([bad]), set(), ["BTCUSDT"])
        assert any(frag in e for e in errs), (bad, errs)
    assert trader.validate_plan(plan_with([trig()] * 9), set(), ["BTCUSDT"])


def test_a_plan_without_triggers_still_validates_for_plans_stored_before_they_existed():
    import test_trader as tt

    d = tt.plan()
    d.pop("triggers", None)
    assert trader.validate_plan(d, set(), ["BTCUSDT"]) == []


def test_triggers_on_the_wrong_side_too_far_away_or_without_a_price_are_dropped_with_a_note():
    kept, notes = trader.reconcile_triggers([trig(), trig(level=99.0), trig(direction="below", level=101.0), trig(level=160.0), trig(instrument="ETHUSDT"), trig()], packet(100.0))
    assert [(k["direction"], k["level"]) for k in kept] == [("above", 105.0)] and kept[0]["price_at_issue"] == 100.0
    assert len(notes) == 4 and any("already beyond" in n for n in notes) and any("more than" in n for n in notes) and any("no price" in n for n in notes)
