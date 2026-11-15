import json
from datetime import timedelta

import pytest

from getrich import config
from getrich.obs.events import utcnow
from getrich.store.db import connect
from getrich.trading import book, gate, limits as L, service
from getrich.trading.sim import SimBroker
from getrich.trading.types import Broker, OrderIntent, PortfolioState, Position

LIMITS_TOML = 'profile = "minimal"\nmax_exposure_fraction = 0.2\naccount_drawdown_halt = 0.15\ndaily_loss_halt = 0.025\n'


def make_limits(**over):
    return L.Limits("minimal", over.get("exposure", 0.2), over.get("dd", 0.15), over.get("daily", 0.025), "x", over.get("risk", L.RISK_PER_TRADE))


def state(**over):
    now = utcnow()
    base = dict(now=now, equity=500.0, cash=500.0, peak_equity=500.0, day_start_equity=500.0, positions={},
                prices={"BTCUSDT": (60000.0, 600.0, "1h"), "ETHUSDT": (2000.0, 600.0, "1h")}, limits_ok=True)
    base.update(over)
    return PortfolioState(**base)


def buy(**over):
    kw = dict(symbol="BTCUSDT", side="buy", stop_price=57000.0)
    kw.update(over)
    return OrderIntent(**kw)


def holding(qty=0.001, price=60000.0, symbol="BTCUSDT"):
    return {symbol: Position(symbol, qty, price, price * 0.95, None, "o_x")}


# ------------------------------------------------------------------ the gate is a pure function that can only tighten


def test_a_buy_is_sized_from_the_risk_budget_and_never_exceeds_it():
    v = gate.evaluate(buy(), state(), make_limits())
    assert v.approved and v.qty == pytest.approx(0.00083)                       # 0.5% of 500 = 2.50 risked over a 3000 stop distance
    assert v.risk_amount <= 500 * L.RISK_PER_TRADE + 1e-9 and v.notional >= 5


def test_a_requested_size_can_only_be_reduced_never_raised():
    assert gate.evaluate(buy(qty=0.01), state(), make_limits()).qty == pytest.approx(0.00083)        # too big: cut to the budget
    assert gate.evaluate(buy(qty=0.0004), state(), make_limits()).qty == pytest.approx(0.0004)       # smaller than the budget: kept
    assert gate.evaluate(buy(risk_fraction=0.05), state(), make_limits()).qty == pytest.approx(0.00083)   # cannot raise the risk fraction
    assert gate.evaluate(buy(risk_fraction=0.001), state(), make_limits()).qty < 0.00083


def test_the_verdict_is_deterministic():
    a, b = gate.evaluate(buy(), state(), make_limits()), gate.evaluate(buy(), state(), make_limits())
    assert a.to_dict() == b.to_dict()


def test_the_exposure_cap_clips_the_size_and_rejects_when_no_room_is_left():
    near = state(positions=holding(qty=90 / 2000, price=2000.0, symbol="ETHUSDT"), prices={"BTCUSDT": (60000.0, 600.0, "1h"), "ETHUSDT": (2000.0, 600.0, "1h")})
    v = gate.evaluate(buy(), near, make_limits())                                # 90 of the 100 allowed is used: 10 left
    assert v.approved and v.notional <= 10.01
    full = state(positions=holding(qty=99 / 2000, price=2000.0, symbol="ETHUSDT"))
    v = gate.evaluate(buy(), full, make_limits())
    assert not v.approved and any("minimum" in r for r in v.reasons)             # the allowed 1 is under the exchange minimum


def test_cash_limits_the_size():
    v = gate.evaluate(buy(stop_price=59000.0), state(cash=20.0), make_limits())
    assert v.approved and v.notional <= 20.0


@pytest.mark.parametrize("stop,fragment", [
    (None, "needs a stop"), (61000.0, "below the current price"), (59800.0, "stop is"), (30000.0, "stop is"), (59500.0, "round-trip costs"),
])
def test_stops_must_exist_sit_below_price_be_sane_and_leave_room_for_costs(stop, fragment):
    v = gate.evaluate(buy(stop_price=stop), state(), make_limits())
    assert not v.approved and fragment in " ".join(v.reasons)


def test_a_claimed_edge_must_beat_the_costs():
    assert not gate.evaluate(buy(expected_edge_fraction=0.004), state(), make_limits()).approved       # round trip is 0.30%; needs 3x
    assert gate.evaluate(buy(expected_edge_fraction=0.02), state(), make_limits()).approved


def test_unknown_symbols_and_sides_are_rejected():
    assert not gate.evaluate(buy(symbol="DOGEUSDT"), state(), make_limits()).approved
    assert not gate.evaluate(buy(side="short"), state(), make_limits()).approved


def test_stale_or_missing_prices_stop_entries():
    old = state(prices={"BTCUSDT": (60000.0, 5 * 3600.0, "1h")})
    assert any("old" in r for r in gate.evaluate(buy(), old, make_limits()).reasons)
    assert any("no stored bars" in r for r in gate.evaluate(buy(symbol="ETHUSDT", stop_price=1900.0), state(prices={}), make_limits()).reasons)


def test_one_position_per_symbol():
    v = gate.evaluate(buy(), state(positions=holding()), make_limits())
    assert not v.approved and any("already holding" in r for r in v.reasons)


@pytest.mark.parametrize("kw,fragment", [
    (dict(killed=True), "kill switch"),
    (dict(limits_ok=False, limits_detail="limits changed since pinned"), "limits changed"),
    (dict(equity=420.0, peak_equity=500.0), "drawdown"),
    (dict(equity=480.0, day_start_equity=500.0), "today's loss"),
    (dict(halt_latched=True), "has not been reset"),
])
def test_halts_and_the_kill_switch_stop_new_entries(kw, fragment):
    v = gate.evaluate(buy(), state(**kw), make_limits() if kw.get("limits_ok", True) else None)
    assert not v.approved and fragment in " ".join(v.reasons)


def test_exits_are_always_allowed_even_halted_or_killed_and_never_larger_than_the_position():
    pos = holding(qty=0.0123)
    bad = state(positions=pos, killed=True, halt_latched=True, limits_ok=False, equity=300.0)
    v = gate.evaluate(OrderIntent("BTCUSDT", "sell"), bad, None)
    assert v.approved and v.qty == pytest.approx(0.0123)
    assert gate.evaluate(OrderIntent("BTCUSDT", "sell", qty=5.0), bad, None).qty == pytest.approx(0.0123)
    assert gate.evaluate(OrderIntent("BTCUSDT", "sell", qty=0.005), bad, None).qty == pytest.approx(0.005)
    assert not gate.evaluate(OrderIntent("BTCUSDT", "sell"), state(), make_limits()).approved       # nothing to sell: spot is long-only


def test_the_conduct_guard_blocks_a_high_cancel_to_fill_ratio():
    assert not gate.evaluate(buy(), state(cancels_24h=10, fills_24h=2), make_limits()).approved
    assert gate.evaluate(buy(), state(cancels_24h=10, fills_24h=5), make_limits()).approved


# ------------------------------------------------------------------ hash-pinned limits


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "config").mkdir(parents=True)
    (h / "config" / "limits.toml").write_text(LIMITS_TOML)
    monkeypatch.setenv("GETRICH_HOME", str(h))
    return h


def test_limits_load_only_when_pinned_and_unchanged(home):
    assert "not pinned" in L.load()[1]
    L.pin()
    lim, why = L.load()
    assert lim and lim.max_exposure_fraction == 0.2 and why == ""
    (home / "config" / "limits.toml").write_text(LIMITS_TOML.replace("0.2\n", "0.9\n", 1))          # someone loosens the file by hand
    assert L.load()[0] is None and "changed since it was pinned" in L.load()[1]


def test_invalid_limits_fail_closed(home):
    (home / "config" / "limits.toml").write_text('profile = "x"\nmax_exposure_fraction = 5\naccount_drawdown_halt = 0.1\ndaily_loss_halt = 0.02\n')
    L.pin()
    assert L.load()[0] is None and "outside" in L.load()[1]
    (home / "config" / "limits.toml").write_text("not toml [[[")
    L.pin()
    assert L.load()[0] is None


# ------------------------------------------------------------------ the order lifecycle against stored bars


def seed_bar(symbol="BTCUSDT", close=60000.0, ts=None, o=None, h=None, l=None, tf="1h"):
    ts = ts or (utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1))
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    ["binance", symbol, tf, ts, o or close, h or close, l or close, close, 1.0, 1.0, 1, utcnow()])
    return ts


@pytest.fixture
def ready(home):
    L.pin()
    seed_bar()
    return home


def events():
    return [json.loads(line) for p in sorted(config.logs_dir().glob("events-*.jsonl")) for line in p.read_text().splitlines()]


def test_propose_approve_fills_with_costs_and_logs_everything_under_one_decision_id(ready):
    oid, v = service.propose(buy(stop_price=57000.0))
    assert v["approved"] and book.get_order(oid)["status"] == "proposed"
    assert book.load_state(["BTCUSDT"]).positions == {}                          # a proposal changes nothing
    res = service.approve(oid)
    assert res["ok"]
    st = book.load_state(["BTCUSDT"])
    pos = st.positions["BTCUSDT"]
    assert pos.avg_price > 60000.0 and pos.stop_price == 57000.0                 # paid slippage
    assert st.equity < 500.0                                                     # and fees
    assert book.get_order(oid)["status"] == "filled"
    ids = {e["decision_id"] for e in events() if e["event"] in ("order.proposed", "risk.verdict", "order.approved", "order.filled")}
    assert len(ids) == 1 and None not in ids


def test_a_rejected_proposal_cannot_be_approved(ready):
    oid, v = service.propose(buy(stop_price=None))
    assert not v["approved"] and book.get_order(oid)["status"] == "rejected_by_gate"
    assert not service.approve(oid)["ok"]


def test_approval_happens_once_and_rejection_by_the_user_sticks(ready):
    oid, _ = service.propose(buy())
    assert service.approve(oid)["ok"] and not service.approve(oid)["ok"]
    oid2, _ = service.propose(buy(symbol="ETHUSDT", stop_price=1900.0)) if seed_bar("ETHUSDT", 2000.0) else (None, None)
    assert service.reject(oid2, "changed my mind")["ok"] and not service.approve(oid2)["ok"]


def test_a_stale_proposal_expires(ready):
    oid, _ = service.propose(buy())
    out = service.approve(oid, now=utcnow() + timedelta(minutes=20))
    assert not out["ok"] and "expired" in out["note"] and book.get_order(oid)["status"] == "expired"


def test_approval_rechecks_the_gate_with_fresh_state(ready):
    oid, _ = service.propose(buy())
    book.kill_path().write_text("x")                                             # the kill switch goes on between proposal and approval
    out = service.approve(oid)
    assert not out["ok"] and "kill switch" in out["note"] and book.load_state(["BTCUSDT"]).positions == {}


def test_a_venue_failure_leaves_no_position_and_is_reported(ready):
    class Broken(SimBroker):
        def buy(self, *a, **k):
            raise ConnectionError("venue down")

    oid, _ = service.propose(buy())
    out = service.approve(oid, broker=Broken())
    assert not out["ok"] and "venue down" in out["note"] and book.get_order(oid)["status"] == "failed"
    assert book.load_state(["BTCUSDT"]).positions == {}
    assert any(e["event"] == "order.failed" for e in events())


def test_exit_is_a_sell_that_closes_the_position(ready):
    service.approve(service.propose(buy())[0])
    oid, v = service.propose(OrderIntent("BTCUSDT", "sell", reason="manual exit"))
    assert v["approved"] and service.approve(oid)["ok"]
    assert book.load_state(["BTCUSDT"]).positions == {}
    assert book.realized_summary()["realized_pnl"] < 0                           # round-trip costs, no price move


def entered(stop=57000.0, tp=None):
    oid, v = service.propose(buy(stop_price=stop, take_profit=tp))
    assert v["approved"], v
    assert service.approve(oid)["ok"]
    return oid


def test_a_touched_stop_closes_the_position_at_the_stop_with_costs(ready):
    entered(57000.0)
    seed_bar(close=57500.0, o=59000.0, h=59500.0, l=56900.0, ts=utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    out = service.tick()
    assert out and out[0]["kind"] == "stop" and 56800 < out[0]["price"] <= 57000
    assert book.load_state(["BTCUSDT"]).positions == {}
    loss = -book.realized_summary()["realized_pnl"]
    assert 2.5 <= loss <= 3.5                                                    # about the 0.5% risk budget plus costs, not more


def test_a_gap_through_the_stop_fills_at_the_worse_open(ready):
    entered(57000.0)
    seed_bar(close=54000.0, o=55000.0, h=55500.0, l=53800.0, ts=utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    assert service.tick()[0]["price"] < 55000.0


def test_when_one_bar_touches_stop_and_take_profit_the_stop_wins(ready):
    entered(57000.0, tp=63000.0)
    seed_bar(close=60000.0, o=60000.0, h=63500.0, l=56500.0, ts=utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    assert service.tick()[0]["kind"] == "stop"


def test_a_take_profit_exits_with_a_gain(ready):
    entered(57000.0, tp=63000.0)
    seed_bar(close=63200.0, o=61000.0, h=63500.0, l=60500.0, ts=utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    assert service.tick()[0]["kind"] == "take_profit" and book.realized_summary()["realized_pnl"] > 0


def test_a_bar_before_the_entry_does_not_trigger_the_stop(ready):
    entered(57000.0)
    assert service.tick() == []                                                  # the only bar is the one the entry was priced from


def test_the_kill_switch_flattens_blocks_and_can_be_lifted(ready):
    entered(57000.0)
    out = service.kill()
    assert out["flattened"] == ["BTCUSDT"] and not out["errors"] and book.load_state(["BTCUSDT"]).positions == {}
    oid, v = service.propose(buy())
    assert not v["approved"] and any("kill switch" in r for r in v["reasons"])
    assert service.unkill() and service.propose(buy())[1]["approved"]


def test_the_kill_switch_blocks_entries_even_if_flattening_fails(ready):
    entered(57000.0)

    class Broken(SimBroker):
        def sell(self, *a, **k):
            raise ConnectionError("down")

    out = service.kill(broker=Broken())
    assert out["errors"] and book.is_killed()


def test_the_drawdown_halt_latches_and_only_unhalt_clears_it(ready):
    with connect() as con:
        con.execute("INSERT INTO equity_snapshots VALUES (?,?,?,?,?)", [utcnow() - timedelta(days=2), "paper", 700.0, 700.0, 0.0])   # a peak of 700
    _, v = service.propose(buy())                                               # equity 500 is 28% below that peak
    assert not v["approved"] and book.is_halted() and any(e["event"] == "risk.halt" for e in events())
    with connect() as con:
        con.execute("DELETE FROM equity_snapshots")                              # even with the peak gone the latch holds
    assert not service.propose(buy())[1]["approved"]
    assert service.unhalt() and service.propose(buy())[1]["approved"]


def test_the_daily_loss_halt_uses_yesterdays_close(ready):
    with connect() as con:
        con.execute("INSERT INTO equity_snapshots VALUES (?,?,?,?,?)", [utcnow() - timedelta(days=1, hours=1), "paper", 520.0, 520.0, 0.0])
    _, v = service.propose(buy())                                               # 500 against 520 at the day's start is -3.8%
    assert not v["approved"] and any("today's loss" in r for r in v["reasons"])


def test_tampering_with_the_limits_file_stops_entries_but_not_exits(ready, home):
    entered(57000.0)
    (home / "config" / "limits.toml").write_text(LIMITS_TOML.replace("0.2\n", "0.9\n", 1))
    assert not service.propose(buy(symbol="ETHUSDT", stop_price=1900.0))[1]["approved"]
    seed_bar("ETHUSDT", 2000.0)
    assert service.propose(OrderIntent("BTCUSDT", "sell"))[1]["approved"]


def test_the_broker_interface_is_complete():
    for name in ("buy", "sell", "poll_exits"):
        with pytest.raises(NotImplementedError):
            getattr(Broker(), name)(*([None] * {"buy": 6, "sell": 5, "poll_exits": 2}[name]))


def test_cli_approval_refuses_without_an_interactive_terminal(ready, capsys, monkeypatch):
    from getrich import cli

    oid, _ = service.propose(buy())
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    assert cli.main(["approve", oid]) == 2
    assert book.get_order(oid)["status"] == "proposed" and "interactive terminal" in capsys.readouterr().out


def test_risk_per_trade_comes_from_the_pinned_limits_and_scales_the_size():
    base = gate.evaluate(buy(), state(), make_limits(exposure=1.0))
    double = gate.evaluate(buy(), state(), make_limits(exposure=1.0, risk=0.01))
    assert double.risk_amount == pytest.approx(2 * base.risk_amount, rel=0.02)
    assert double.risk_amount <= 500 * 0.01 + 1e-9


def test_a_limits_file_carries_risk_per_trade_and_rejects_nonsense(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "limits_path", lambda: tmp_path / "limits.toml")
    monkeypatch.setattr(L, "pin_path", lambda: tmp_path / "limits.pin")
    body = 'profile = "moderate"\nmax_exposure_fraction = 0.5\naccount_drawdown_halt = 0.3\ndaily_loss_halt = 0.055\n'
    (tmp_path / "limits.toml").write_text(body + "risk_per_trade = 0.02\n")
    L.pin()
    lim, why = L.load()
    assert lim is not None and lim.risk_per_trade == 0.02 and why == ""
    (tmp_path / "limits.toml").write_text(body)                                   # an older file without the field keeps the default
    L.pin()
    assert L.load()[0].risk_per_trade == L.RISK_PER_TRADE
    (tmp_path / "limits.toml").write_text(body + "risk_per_trade = 0.5\n")       # 50% per trade is refused
    L.pin()
    lim, why = L.load()
    assert lim is None and "outside their allowed range" in why


def test_a_limits_file_carries_leverage_and_shorting_and_rejects_nonsense(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "limits_path", lambda: tmp_path / "limits.toml")
    monkeypatch.setattr(L, "pin_path", lambda: tmp_path / "limits.pin")
    body = 'profile = "aggressive"\naccount_drawdown_halt = 0.3\ndaily_loss_halt = 0.055\n'

    def load(extra):
        (tmp_path / "limits.toml").write_text(body + extra)
        L.pin()
        return L.load()

    lim, why = load("max_exposure_fraction = 2.0\nmax_leverage = 3.0\nallow_short = true\n")
    assert lim is not None and lim.max_leverage == 3.0 and lim.allow_short is True and lim.max_exposure_fraction == 2.0
    lim, _ = load("max_exposure_fraction = 0.5\n")                                # an older file stays spot-only
    assert lim.max_leverage == 1.0 and lim.allow_short is False
    assert load("max_exposure_fraction = 2.0\n")[0] is None                        # exposure above 1x needs leverage that allows it
    assert load("max_exposure_fraction = 4.0\nmax_leverage = 3.0\n")[0] is None   # exposure above the leverage cap
    assert load("max_exposure_fraction = 2.0\nmax_leverage = 50.0\n")[0] is None   # above the hard ceiling
