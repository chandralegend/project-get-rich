"""Binance SPOT TESTNET broker. Virtual money only; the base URL is locked to the testnet host and there is no live mode.

Facts below come from Binance's own docs as read on 2026-11-14 (see docs/phase4-findings.md): signed endpoints take an
HMAC-SHA256 hex signature over the full query/body string including `timestamp`, the key goes in `X-MBX-APIKEY`, the
current OCO endpoint is POST /api/v3/orderList/oco, filters come from GET /api/v3/exchangeInfo.

Safety rules in this file:
  * keys come from the environment (GETRICH_BINANCE_TESTNET_KEY / _SECRET) and are never logged or put in events;
  * orders are never retried blindly: each carries a client order id, and an ambiguous failure is resolved by looking the
    order up, so a timeout cannot place two orders;
  * a position is never left without its protective stop: if the stop cannot be placed after a buy, the position is sold
    at market straight away and the error is raised loudly.
Only market buys are placed, with exchange-side market stops (STOP_LOSS) so an exit is guaranteed rather than a limit that might not fill.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from ..obs.events import emit, utcnow
from .types import Broker, FillInfo, Position, SymbolRules

BASE_URL = "https://testnet.binance.vision"
SERVICE = "broker.testnet"
BASES = {"BTCUSDT": ("BTC", "USDT"), "ETHUSDT": ("ETH", "USDT")}


class VenueError(RuntimeError):
    def __init__(self, status: int, code: int | None, msg: str):
        super().__init__(f"binance testnet error http {status} code {code}: {msg}")
        self.status, self.code, self.msg = status, code, msg


def _floor(x: float, step: float) -> float:
    return math.floor(round(x / step, 9)) * step if step > 0 else x


def _dec(x: float, step: float) -> str:
    """Format a number to the precision of a step size, as the exchange wants strings without float noise."""
    places = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return f"{_floor(x, step):.{places}f}"


class BinanceTestnetBroker(Broker):
    venue = "testnet"

    def __init__(self, key: str | None = None, secret: str | None = None, client: httpx.Client | None = None, base_url: str = BASE_URL):
        if base_url.rstrip("/") != BASE_URL:
            raise ValueError("this broker only talks to the Binance Spot TESTNET")
        self._key = key or os.environ.get("GETRICH_BINANCE_TESTNET_KEY", "")
        self._secret = secret or os.environ.get("GETRICH_BINANCE_TESTNET_SECRET", "")
        if not self._key or not self._secret:
            raise RuntimeError("set GETRICH_BINANCE_TESTNET_KEY and GETRICH_BINANCE_TESTNET_SECRET in .env (free keys: testnet.binance.vision)")
        self._http = client or httpx.Client(base_url=BASE_URL, timeout=20)
        self._offset_ms = 0
        self._rules: dict[str, SymbolRules] = {}

    # ---------------------------------------------------------------- transport
    def _sign(self, params: dict) -> str:
        return hmac.new(self._secret.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False, _retry: bool = True):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"X-MBX-APIKEY": self._key}
        if signed:
            params["timestamp"] = int(time.time() * 1000) + self._offset_ms
            params["recvWindow"] = 5000
            params["signature"] = self._sign(params)
        resp = self._http.request(method, path, params=params if method in ("GET", "DELETE") else None,
                                  data=params if method == "POST" else None, headers=headers)
        if resp.status_code in (418, 429):
            raise VenueError(resp.status_code, None, f"rate limited, retry after {resp.headers.get('Retry-After', '?')}s: stop and wait")
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code >= 400:
            code, msg = (body.get("code"), body.get("msg")) if isinstance(body, dict) else (None, resp.text[:120])
            if code == -1021 and _retry:                                  # our clock is off: sync once and retry (not an order-state ambiguity)
                self._offset_ms = int(self._request("GET", "/api/v3/time")["serverTime"]) - int(time.time() * 1000)
                return self._request(method, path, params if not signed else {k: v for k, v in params.items() if k not in ("timestamp", "recvWindow", "signature")}, signed, _retry=False)
            raise VenueError(resp.status_code, code, str(msg))
        return body

    def last_price(self, symbol: str) -> float:
        return float(self._request("GET", "/api/v3/ticker/price", {"symbol": symbol})["price"])

    # ---------------------------------------------------------------- exchange rules
    def symbol_rules(self) -> dict[str, SymbolRules]:
        for sym in BASES:
            if sym not in self._rules:
                info = self._request("GET", "/api/v3/exchangeInfo", {"symbol": sym})["symbols"][0]
                f = {x["filterType"]: x for x in info["filters"]}
                notional = f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}
                self._rules[sym] = SymbolRules(step=float(f["LOT_SIZE"]["stepSize"]), tick=float(f["PRICE_FILTER"]["tickSize"]),
                                               min_qty=float(f["LOT_SIZE"]["minQty"]), min_notional=float(notional.get("minNotional", 5.0)))
        return dict(self._rules)

    # ---------------------------------------------------------------- orders
    def _lookup(self, symbol: str, client_id: str) -> dict | None:
        try:
            return self._request("GET", "/api/v3/order", {"symbol": symbol, "origClientOrderId": client_id}, signed=True)
        except VenueError as exc:
            if exc.code == -2013:                                         # order does not exist
                return None
            raise

    def _market_order(self, symbol: str, side: str, qty: float, client_id: str) -> dict:
        rules = self.symbol_rules()[symbol]
        params = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": _dec(qty, rules.step),
                  "newClientOrderId": client_id, "newOrderRespType": "FULL"}
        try:
            return self._request("POST", "/api/v3/order", params, signed=True)
        except VenueError as exc:
            if exc.status >= 500 or exc.code == -1007:                    # execution status UNKNOWN: look it up, never resend blindly
                found = self._lookup(symbol, client_id)
                if found and found.get("status") == "FILLED":
                    return found
                if found is None:
                    raise VenueError(exc.status, exc.code, "order was not placed (confirmed by lookup)") from exc
                raise VenueError(exc.status, exc.code, f"order state unclear: {found.get('status')}") from exc
            raise

    def _fills_from(self, symbol: str, resp: dict, kind: str) -> list[FillInfo]:
        """Convert exchange fills. A buy fee paid in the base asset reduces what we actually hold, so it is folded into the price."""
        base, quote = BASES[symbol]
        raw = resp.get("fills") or []
        ts = datetime.fromtimestamp(resp.get("transactTime", time.time() * 1000) / 1000, tz=timezone.utc)
        if not raw:
            qty, quote_spent = float(resp.get("executedQty", 0)), float(resp.get("cummulativeQuoteQty", 0))
            return [FillInfo(quote_spent / qty, qty, 0.0, ts, kind, str(resp.get("orderId", "")))] if qty else []
        qty = sum(float(f["qty"]) for f in raw)
        gross = sum(float(f["qty"]) * float(f["price"]) for f in raw)
        fee_quote = sum(float(f["commission"]) for f in raw if f["commissionAsset"] == quote)
        fee_base = sum(float(f["commission"]) for f in raw if f["commissionAsset"] == base)
        fee_other = [f["commissionAsset"] for f in raw if f["commissionAsset"] not in (base, quote)]
        if fee_other:                                                      # e.g. BNB: no price to convert with here, so estimate at the standard 10 bps
            fee_quote += gross * 0.001
            emit("broker.fee_estimated", service=SERVICE, level="warn", asset=fee_other[0])
        if resp.get("side") == "BUY" and fee_base:
            net = qty - fee_base
            return [FillInfo(gross / net, net, fee_quote, ts, kind, str(resp.get("orderId", "")))]
        if resp.get("side") == "SELL" and fee_base:
            fee_quote += fee_base * (gross / qty)
        return [FillInfo(gross / qty, qty, fee_quote, ts, kind, str(resp.get("orderId", "")))]

    def buy(self, symbol, qty, ref_price, stop, take_profit, client_id):
        rules = self.symbol_rules()[symbol]
        resp = self._market_order(symbol, "BUY", qty, client_id)
        fills = self._fills_from(symbol, resp, "entry")
        held = _floor(sum(f.qty for f in fills), rules.step)
        try:
            self._protect(symbol, held, stop, take_profit, client_id, rules)
        except Exception as exc:                                           # never hold an unprotected position
            emit("broker.protect_failed", service=SERVICE, level="error", symbol=symbol, error=repr(exc)[:200])
            try:
                out = self._market_order(symbol, "SELL", held, client_id + "-fl")
                self._cancel_all(symbol)
                emit("broker.flattened_after_protect_failure", service=SERVICE, level="error", symbol=symbol, order_id=out.get("orderId"))
            except Exception as exc2:
                emit("broker.unprotected_position", service=SERVICE, level="error", symbol=symbol, qty=held, error=repr(exc2)[:200])
                raise RuntimeError(f"UNPROTECTED POSITION in {symbol}: stop placement failed ({exc!r}) and so did flattening ({exc2!r}). Close it on the testnet by hand.") from exc2
            raise RuntimeError(f"protective stop could not be placed ({exc!r}); the position was sold again at market. Nothing is held.") from exc
        return fills

    def _protect(self, symbol: str, qty: float, stop: float | None, take_profit: float | None, client_id: str, rules: SymbolRules) -> None:
        if stop is None:
            raise ValueError("a position needs a stop")
        q, tick = _dec(qty, rules.step), rules.tick
        if take_profit is not None:     # OCO: take-profit leg above, market stop leg below (the current endpoint, not the deprecated /order/oco)
            self._request("POST", "/api/v3/orderList/oco", {
                "symbol": symbol, "side": "SELL", "quantity": q, "listClientOrderId": client_id + "-oco",
                "aboveType": "LIMIT_MAKER", "abovePrice": _dec(take_profit, tick),
                "belowType": "STOP_LOSS", "belowStopPrice": _dec(stop, tick), "newOrderRespType": "ACK"}, signed=True)
        else:
            self._request("POST", "/api/v3/order", {
                "symbol": symbol, "side": "SELL", "type": "STOP_LOSS", "quantity": q, "stopPrice": _dec(stop, tick),
                "newClientOrderId": client_id + "-stop", "newOrderRespType": "ACK"}, signed=True)

    def _cancel_all(self, symbol: str) -> list:
        return self._request("DELETE", "/api/v3/openOrders", {"symbol": symbol}, signed=True) or []

    def sell(self, symbol, qty, ref_price, kind, client_id):
        base, _quote = BASES[symbol]
        rules = self.symbol_rules()[symbol]
        cancelled = self._cancel_all(symbol)                               # the protective order holds the balance: release it first
        if cancelled:
            emit("broker.protective_cancelled", service=SERVICE, symbol=symbol, n=len(cancelled), reason=kind)
        acct = self._request("GET", "/api/v3/account", signed=True)
        free = next((float(b["free"]) for b in acct["balances"] if b["asset"] == base), 0.0)
        sell_qty = _floor(min(qty, free), rules.step)
        if sell_qty < rules.min_qty:
            raise RuntimeError(f"free {base} balance {free} is below the minimum order size: nothing to sell")
        return self._fills_from(symbol, self._market_order(symbol, "SELL", sell_qty, client_id), kind)

    def poll_exits(self, positions: dict[str, Position], now: datetime):
        out = []
        for sym, pos in positions.items():
            if self._request("GET", "/api/v3/openOrders", {"symbol": sym}, signed=True):
                continue                                                   # protective order still resting: nothing happened
            start = int((pos.entry_ts or now).timestamp() * 1000)
            trades = [t for t in self._request("GET", "/api/v3/myTrades", {"symbol": sym, "startTime": start}, signed=True) if not t["isBuyer"]]
            if not trades:                                                 # no resting order and no sale: someone or something removed the stop
                emit("broker.stop_missing", service=SERVICE, level="error", symbol=sym, order_id=pos.order_id)
                continue
            qty = sum(float(t["qty"]) for t in trades)
            price = sum(float(t["qty"]) * float(t["price"]) for t in trades) / qty
            fee = sum(float(t["commission"]) for t in trades if t["commissionAsset"] == "USDT")
            kind = "stop" if pos.stop_price is not None and price <= pos.stop_price * 1.002 else "take_profit"
            out.append((sym, FillInfo(price, qty, fee, datetime.fromtimestamp(max(t["time"] for t in trades) / 1000, tz=timezone.utc), kind, str(trades[-1]["orderId"]))))
        return out
