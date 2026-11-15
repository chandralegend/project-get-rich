"""Order lifecycle: propose -> risk gate -> (you) approve or reject -> broker. Nothing here submits an order on its own.

The gate runs twice: when an order is proposed, and again on approval with fresh state, because prices and the account
move. On approval the size can only shrink compared with the proposal. A proposal goes stale after 15 minutes.
Every step is written to the event log under the proposal's decision_id.
"""

from __future__ import annotations

from datetime import timedelta

from ..ids import new_id
from ..obs.events import emit, utcnow
from . import book, gate, limits as L
from .sim import SimBroker
from .types import Broker, OrderIntent

SERVICE = "trading"


def _symbols(*extra):
    return {s for s in extra if s} | {"BTCUSDT", "ETHUSDT"}


def _state(broker: Broker, symbols, now):
    """Portfolio state for a venue. A venue with its own market (the testnet's prices differ from mainnet) supplies its own prices."""
    state = book.load_state(symbols, now, broker.venue)
    if hasattr(broker, "last_price"):
        for sym in symbols:
            state.prices[sym] = (broker.last_price(sym), 0.0, "live")
        state.equity = state.cash + sum(p.qty * state.prices.get(p.symbol, (p.avg_price,))[0] for p in state.positions.values())
        state.peak_equity = max(state.peak_equity, state.equity)
    return state


def _latch_if_tripped(state, lim) -> bool:
    """Drawdown at or past the halt: latch it so it survives a recovery in equity. Only `unhalt` clears it."""
    if lim is None or state.peak_equity <= 0 or state.halt_latched:
        return False
    dd = (state.peak_equity - state.equity) / state.peak_equity
    if dd < lim.account_drawdown_halt:
        return False
    book.halt_path().parent.mkdir(parents=True, exist_ok=True)
    book.halt_path().write_text(f"{state.now.isoformat()} drawdown {dd:.2%}\n")
    emit("risk.halt", service=SERVICE, level="error", kind="drawdown", equity=state.equity, peak=state.peak_equity, drawdown=dd)
    return True


def propose(intent: OrderIntent, *, broker: Broker | None = None, now=None) -> tuple[str, dict]:
    """Run the gate and store the proposal. Returns (order_id, verdict as a dict). Nothing is sent to any venue."""
    broker, now = broker or SimBroker(), now or utcnow()
    state = _state(broker, _symbols(intent.symbol), now)
    lim, _why = L.load()
    verdict = gate.evaluate(intent, state, lim, rules=broker.symbol_rules())
    if intent.side.lower() in ("short", "cover") and verdict.approved:        # the book and brokers here are spot only: fail closed rather than mis-account a short
        verdict.approved, verdict.qty = False, 0.0
        verdict.reasons.append("margin_venue: shorting is not wired into the paper or testnet path yet (replay only)")
    order_id = new_id("o")
    status = "proposed" if verdict.approved else "rejected_by_gate"
    ref = state.prices.get(intent.symbol, (None,))[0]
    book.insert_order(order_id, intent, broker.venue, status, verdict.qty, ref, verdict.to_dict(), now)
    book.snapshot(state, broker.venue)
    emit("order.proposed", service=SERVICE, decision_id=intent.decision_id, order_id=order_id, symbol=intent.symbol, side=intent.side,
         qty=verdict.qty, source=intent.source, reason=intent.reason[:200])
    emit("risk.verdict", service=SERVICE, level="info" if verdict.approved else "warn", decision_id=intent.decision_id, order_id=order_id,
         approved=verdict.approved, reasons=verdict.reasons, halted=verdict.halted)
    _latch_if_tripped(state, lim)
    return order_id, verdict.to_dict()


def approve(order_id: str, *, broker: Broker | None = None, now=None) -> dict:
    broker, now = broker or SimBroker(), now or utcnow()
    o = book.get_order(order_id)
    if o is None:
        return {"ok": False, "note": f"no such order {order_id}"}
    if o["status"] != "proposed":
        return {"ok": False, "note": f"order is {o['status']}, not proposed"}
    if o["venue"] != broker.venue:
        return {"ok": False, "note": f"order is for venue {o['venue']}, not {broker.venue}"}
    if now - o["created_at"] > timedelta(seconds=L.PROPOSAL_TTL_S):
        book.set_status(order_id, "expired", now, "not approved within 15 minutes")
        emit("order.expired", service=SERVICE, decision_id=o["decision_id"], order_id=order_id)
        return {"ok": False, "note": "proposal expired (older than 15 minutes); propose again at the current price"}

    intent = OrderIntent(o["symbol"], o["side"], o["stop_price"], o["take_profit"], qty=o["qty"], source=o["source"], reason=o["reason"], decision_id=o["decision_id"])
    state = _state(broker, _symbols(o["symbol"]), now)
    lim, _why = L.load()
    verdict = gate.evaluate(intent, state, lim, rules=broker.symbol_rules())                       # fresh state; qty can only come out equal or smaller
    if not verdict.approved:
        book.set_status(order_id, "rejected_by_gate", now, "; ".join(verdict.reasons)[:300])
        emit("risk.verdict", service=SERVICE, level="warn", decision_id=o["decision_id"], order_id=order_id, approved=False, reasons=verdict.reasons, stage="approval")
        return {"ok": False, "note": "the risk gate now rejects this order: " + "; ".join(verdict.reasons), "verdict": verdict.to_dict()}
    qty = min(verdict.qty, o["qty"])
    ref = state.prices[o["symbol"]][0]
    emit("order.approved", service=SERVICE, decision_id=o["decision_id"], order_id=order_id, qty=qty)
    try:
        if o["side"] == "buy":
            fills = broker.buy(o["symbol"], qty, ref, o["stop_price"], o["take_profit"], order_id)
        else:
            fills = broker.sell(o["symbol"], qty, ref, "exit", order_id)
    except Exception as exc:                                          # a venue failure must never leave a silent half-state
        book.set_status(order_id, "failed", now, repr(exc)[:300])
        emit("order.failed", service=SERVICE, level="error", decision_id=o["decision_id"], order_id=order_id, error=repr(exc)[:300])
        return {"ok": False, "note": f"the venue failed: {exc!r}. Check the venue's own state before retrying."}
    book.record_fills(order_id, o["symbol"], o["side"], fills, broker.venue)
    book.set_status(order_id, "filled" if o["side"] == "buy" else "closed", now, qty=sum(f.qty for f in fills))
    after = _state(broker, _symbols(o["symbol"]), utcnow())
    book.snapshot(after, broker.venue)
    _latch_if_tripped(after, lim)
    for f in fills:
        emit("order.filled", service=SERVICE, decision_id=o["decision_id"], order_id=order_id, symbol=o["symbol"], side=o["side"], qty=f.qty, price=f.price, fee=f.fee)
    return {"ok": True, "note": "filled", "fills": [(f.qty, f.price, f.fee) for f in fills], "equity": after.equity}


def reject(order_id: str, reason: str = "", *, now=None) -> dict:
    now = now or utcnow()
    o = book.get_order(order_id)
    if o is None or o["status"] != "proposed":
        return {"ok": False, "note": f"order {order_id} is not a pending proposal"}
    book.set_status(order_id, "rejected_by_user", now, reason)
    emit("order.rejected", service=SERVICE, decision_id=o["decision_id"], order_id=order_id, reason=reason[:200])
    return {"ok": True, "note": "rejected"}


def tick(*, broker: Broker | None = None, now=None) -> list[dict]:
    """Look for protective stops and take profits that triggered since the last look, record them, and snapshot equity."""
    broker, now = broker or SimBroker(), now or utcnow()
    state = _state(broker, _symbols(), now)
    closed = []
    for sym, fill in broker.poll_exits(state.positions, now):
        pos = state.positions[sym]
        book.record_fills(pos.order_id, sym, "sell", [fill], broker.venue)
        book.set_status(pos.order_id, "closed", now, fill.kind)
        o = book.get_order(pos.order_id)
        emit("position.exited", service=SERVICE, level="warn" if fill.kind == "stop" else "info", decision_id=o["decision_id"] if o else None,
             order_id=pos.order_id, symbol=sym, kind=fill.kind, price=fill.price, qty=fill.qty)
        closed.append({"symbol": sym, "kind": fill.kind, "price": fill.price, "qty": fill.qty})
    after = _state(broker, _symbols(), utcnow())
    book.snapshot(after, broker.venue)
    _latch_if_tripped(after, L.load()[0])
    return closed


def kill(*, broker: Broker | None = None, now=None) -> dict:
    """Flatten every position and block new ones. Needs only the local files, no network and no model."""
    broker, now = broker or SimBroker(), now or utcnow()
    book.kill_path().parent.mkdir(parents=True, exist_ok=True)
    book.kill_path().write_text(now.isoformat() + "\n")               # blocks entries first, so a failure below still leaves it blocked
    emit("risk.kill", service=SERVICE, level="error", action="on")
    state = _state(broker, _symbols(), now)
    flattened, errors = [], []
    for sym, pos in state.positions.items():
        try:
            ref = state.prices.get(sym, (pos.avg_price,))[0]
            fills = broker.sell(sym, pos.qty, ref, "flatten", new_id("o"))
            book.record_fills(pos.order_id, sym, "sell", fills, broker.venue)
            book.set_status(pos.order_id, "closed", now, "flattened by kill switch")
            flattened.append(sym)
        except Exception as exc:
            errors.append(f"{sym}: {exc!r}")
            emit("order.failed", service=SERVICE, level="error", symbol=sym, error=repr(exc)[:300], during="kill")
    book.snapshot(_state(broker, _symbols(), utcnow()), broker.venue)
    return {"flattened": flattened, "errors": errors}


def unhalt() -> bool:
    existed = book.halt_path().exists()
    book.halt_path().unlink(missing_ok=True)
    emit("risk.halt", service=SERVICE, level="warn", kind="drawdown", action="reset_by_owner", was_latched=existed)
    return existed


def unkill() -> bool:
    existed = book.kill_path().exists()
    book.kill_path().unlink(missing_ok=True)
    emit("risk.kill", service=SERVICE, action="off", was_on=existed)
    return existed
