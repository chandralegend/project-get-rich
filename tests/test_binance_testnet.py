import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import parse_qsl

import httpx
import pytest

from getrich.obs.events import utcnow
from getrich.trading import book, limits as L, service
from getrich.trading.binance_testnet import BASE_URL, BinanceTestnetBroker, VenueError
from getrich.trading.types import OrderIntent, Position

SECRET = "test-secret"
INFO = {"symbols": [{"symbol": "BTCUSDT", "filters": [
    {"filterType": "LOT_SIZE", "minQty": "0.00001000", "maxQty": "9000", "stepSize": "0.00001000"},
    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
    {"filterType": "NOTIONAL", "minNotional": "5.00000000"}]}]}


class FakeExchange:
    """Just enough of the Spot testnet to check what the broker sends and how it reads the answers."""

    def __init__(self, price=60000.0, fee_asset="BTC", fail=None, free_btc=0.00119, open_orders=None, trades=None, status_down_once=False):
        self.price, self.fee_asset, self.fail, self.free_btc = price, fee_asset, fail or {}, free_btc
        self.requests, self.open_orders, self.trades, self.down_once = [], open_orders if open_orders is not None else [], trades or [], status_down_once
        self.client = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(self.handle))

    def sent(self, method, path):
        return [r for r in self.requests if r["method"] == method and r["path"] == path]

    def handle(self, request):
        path = request.url.path
        raw = request.content.decode() if request.method == "POST" else request.url.query.decode()
        params = dict(parse_qsl(raw))
        self.requests.append({"method": request.method, "path": path, "params": params, "headers": dict(request.headers), "raw": raw})
        key = f"{request.method} {path}"
        if key in self.fail:
            f = self.fail[key]
            if f.get("once") and self.requests.count(None):
                pass
            return httpx.Response(f["status"], json=f.get("body", {"code": f.get("code", -1), "msg": f.get("msg", "boom")}))
        if path == "/api/v3/exchangeInfo":
            return httpx.Response(200, json=INFO)
        if path == "/api/v3/ticker/price":
            return httpx.Response(200, json={"symbol": "BTCUSDT", "price": str(self.price)})
        if key == "POST /api/v3/order":
            if params["type"] == "MARKET":
                qty = float(params["quantity"])
                fee = qty * 0.001 if self.fee_asset == "BTC" else qty * self.price * 0.001
                return httpx.Response(200, json={"symbol": "BTCUSDT", "orderId": 11, "clientOrderId": params["newClientOrderId"], "transactTime": 1760000000000,
                                                 "executedQty": params["quantity"], "cummulativeQuoteQty": str(qty * self.price), "status": "FILLED", "side": params["side"],
                                                 "fills": [{"price": str(self.price), "qty": params["quantity"], "commission": f"{fee:.8f}", "commissionAsset": self.fee_asset, "tradeId": 1}]})
            return httpx.Response(200, json={"symbol": "BTCUSDT", "orderId": 12, "clientOrderId": params["newClientOrderId"], "transactTime": 1760000000001})
        if key == "POST /api/v3/orderList/oco":
            return httpx.Response(200, json={"orderListId": 5, "listStatusType": "EXEC_STARTED"})
        if key == "DELETE /api/v3/openOrders":
            return httpx.Response(200, json=[{"orderId": 12}] if self.open_orders else [])
        if key == "GET /api/v3/openOrders":
            return httpx.Response(200, json=self.open_orders)
        if key == "GET /api/v3/account":
            return httpx.Response(200, json={"balances": [{"asset": "BTC", "free": str(self.free_btc), "locked": "0"}, {"asset": "USDT", "free": "10000", "locked": "0"}]})
        if key == "GET /api/v3/myTrades":
            return httpx.Response(200, json=self.trades)
        if key == "GET /api/v3/time":
            return httpx.Response(200, json={"serverTime": 1760000000000})
        return httpx.Response(404, json={"code": -1, "msg": f"unexpected {key}"})


def broker(ex):
    return BinanceTestnetBroker("KEY123", SECRET, client=ex.client)


def check_signature(req):
    params = [(k, v) for k, v in parse_qsl(req["raw"]) if k != "signature"]
    expected = hmac.new(SECRET.encode(), "&".join(f"{k}={v}" for k, v in params).encode(), hashlib.sha256).hexdigest()
    return dict(parse_qsl(req["raw"]))["signature"] == expected


def test_it_only_talks_to_the_testnet_and_needs_keys(monkeypatch):
    with pytest.raises(ValueError):
        BinanceTestnetBroker("k", "s", base_url="https://api.binance.com")
    monkeypatch.delenv("GETRICH_BINANCE_TESTNET_KEY", raising=False)
    monkeypatch.delenv("GETRICH_BINANCE_TESTNET_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="GETRICH_BINANCE_TESTNET_KEY"):
        BinanceTestnetBroker()


def test_exchange_filters_become_symbol_rules():
    r = broker(FakeExchange()).symbol_rules()["BTCUSDT"]
    assert (r.step, r.tick, r.min_qty, r.min_notional) == (1e-5, 0.01, 1e-5, 5.0)


def test_signed_requests_carry_the_key_header_timestamp_and_a_valid_signature():
    ex = FakeExchange()
    b = broker(ex)
    b.buy("BTCUSDT", 0.00119, 60000.0, 57000.0, None, "o_abc")
    order = ex.sent("POST", "/api/v3/order")[0]
    assert order["headers"]["x-mbx-apikey"] == "KEY123" and "timestamp" in order["params"] and order["params"]["recvWindow"] == "5000"
    assert check_signature(order) and SECRET not in order["raw"] and "KEY123" not in order["raw"]


def test_a_buy_places_a_market_order_then_an_exchange_side_market_stop_and_folds_a_base_asset_fee_into_the_fill():
    ex = FakeExchange(fee_asset="BTC")
    fills = broker(ex).buy("BTCUSDT", 0.00119, 60000.0, 57000.0, None, "o_abc")
    market, stop = ex.sent("POST", "/api/v3/order")
    assert market["params"]["type"] == "MARKET" and market["params"]["side"] == "BUY" and market["params"]["quantity"] == "0.00119"
    assert market["params"]["newClientOrderId"] == "o_abc" and market["params"]["newOrderRespType"] == "FULL"
    assert stop["params"]["type"] == "STOP_LOSS" and stop["params"]["side"] == "SELL" and stop["params"]["stopPrice"] == "57000.00"
    assert stop["params"]["quantity"] == "0.00118"                                 # what we actually hold after the 0.1% fee taken in BTC
    assert check_signature(stop)
    f = fills[0]
    assert f.qty == pytest.approx(0.00119 * 0.999) and f.fee == 0.0 and f.price > 60000.0     # the fee is in the price: cash out is right


def test_a_quote_asset_fee_is_kept_as_a_fee():
    ex = FakeExchange(fee_asset="USDT")
    f = broker(ex).buy("BTCUSDT", 0.00119, 60000.0, 57000.0, None, "o_abc")[0]
    assert f.qty == pytest.approx(0.00119) and f.fee == pytest.approx(0.00119 * 60000 * 0.001)
    assert ex.sent("POST", "/api/v3/order")[1]["params"]["quantity"] == "0.00119"


def test_stop_plus_take_profit_uses_the_current_oco_endpoint():
    ex = FakeExchange()
    broker(ex).buy("BTCUSDT", 0.00119, 60000.0, 57000.0, 66000.0, "o_abc")
    oco = ex.sent("POST", "/api/v3/orderList/oco")[0]["params"]
    assert (oco["aboveType"], oco["abovePrice"], oco["belowType"], oco["belowStopPrice"]) == ("LIMIT_MAKER", "66000.00", "STOP_LOSS", "57000.00")
    assert oco["side"] == "SELL" and not ex.sent("POST", "/api/v3/order/oco")


def test_if_the_stop_cannot_be_placed_the_position_is_sold_again_and_the_error_is_loud():
    ex = FakeExchange(fail={"POST /api/v3/orderList/oco": {"status": 400, "code": -1013, "msg": "Filter failure: PRICE_FILTER"}})
    with pytest.raises(RuntimeError, match="sold again at market"):
        broker(ex).buy("BTCUSDT", 0.00119, 60000.0, 57000.0, 66000.0, "o_abc")
    sells = [r for r in ex.sent("POST", "/api/v3/order") if r["params"]["side"] == "SELL"]
    assert len(sells) == 1 and sells[0]["params"]["type"] == "MARKET" and sells[0]["params"]["newClientOrderId"] == "o_abc-fl"


def test_if_the_stop_and_the_flatten_both_fail_it_says_the_position_is_unprotected():
    class Both(FakeExchange):
        def handle(self, request):
            if request.url.path == "/api/v3/orderList/oco" or (request.method == "POST" and request.url.path == "/api/v3/order" and b"SELL" in request.content):
                return httpx.Response(400, json={"code": -2010, "msg": "nope"})
            return super().handle(request)

    ex = Both()
    with pytest.raises(RuntimeError, match="UNPROTECTED POSITION"):
        broker(ex).buy("BTCUSDT", 0.00119, 60000.0, 57000.0, 66000.0, "o_abc")


def test_a_server_error_on_an_order_is_resolved_by_lookup_never_by_resending():
    class Flaky(FakeExchange):
        def handle(self, request):
            if request.method == "POST" and request.url.path == "/api/v3/order" and b"MARKET" in request.content:
                self.requests.append({"method": "POST", "path": "/api/v3/order", "params": dict(parse_qsl(request.content.decode())), "headers": {}, "raw": ""})
                return httpx.Response(503, json={"code": -1007, "msg": "Timeout waiting for response from backend server"})
            if request.method == "GET" and request.url.path == "/api/v3/order":
                return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist."})
            return super().handle(request)

    ex = Flaky()
    with pytest.raises(VenueError, match="not placed"):
        broker(ex).buy("BTCUSDT", 0.00119, 60000.0, 57000.0, None, "o_abc")
    assert len(ex.sent("POST", "/api/v3/order")) == 1                              # exactly one attempt


def test_rate_limits_stop_everything_with_the_retry_hint():
    ex = FakeExchange(fail={"GET /api/v3/exchangeInfo": {"status": 429, "body": {"code": -1003, "msg": "Too many requests"}}})
    with pytest.raises(VenueError, match="rate limited"):
        broker(ex).symbol_rules()


def test_selling_releases_the_protective_order_first_and_sells_no_more_than_is_free():
    ex = FakeExchange(open_orders=[{"orderId": 12}], free_btc=0.00118)
    fills = broker(ex).sell("BTCUSDT", 0.00119, 60000.0, "exit", "o_exit")
    order = [(r["method"], r["path"]) for r in ex.requests if r["path"] in ("/api/v3/openOrders", "/api/v3/order", "/api/v3/account")]
    assert order[0] == ("DELETE", "/api/v3/openOrders") and order[-1] == ("POST", "/api/v3/order")
    assert ex.sent("POST", "/api/v3/order")[0]["params"]["quantity"] == "0.00118" and fills[0].kind == "exit"


def test_poll_exits_sees_nothing_while_the_stop_rests_and_reports_a_triggered_stop():
    pos = {"BTCUSDT": Position("BTCUSDT", 0.00118, 60000.0, 57000.0, None, "o_abc", utcnow() - timedelta(hours=2))}
    resting = FakeExchange(open_orders=[{"orderId": 12}])
    assert broker(resting).poll_exits(pos, utcnow()) == []
    triggered = FakeExchange(open_orders=[], trades=[{"isBuyer": True, "qty": "0.00119", "price": "60000", "commission": "0", "commissionAsset": "BTC", "time": 1, "orderId": 11},
                                                     {"isBuyer": False, "qty": "0.00118", "price": "56990", "commission": "0.067", "commissionAsset": "USDT", "time": 1760000100000, "orderId": 12}])
    (sym, fill), = broker(triggered).poll_exits(pos, utcnow())
    assert sym == "BTCUSDT" and fill.kind == "stop" and fill.price == pytest.approx(56990) and fill.fee == pytest.approx(0.067)


def test_a_missing_protective_order_with_no_sale_is_reported_not_ignored():
    pos = {"BTCUSDT": Position("BTCUSDT", 0.00118, 60000.0, 57000.0, None, "o_abc", utcnow() - timedelta(hours=2))}
    assert broker(FakeExchange(open_orders=[], trades=[])).poll_exits(pos, utcnow()) == []
    import glob, os
    from getrich import config

    assert any('"broker.stop_missing"' in open(p).read() for p in glob.glob(str(config.logs_dir() / "events-*.jsonl")))


def test_a_clock_error_syncs_once_and_retries_the_request():
    class Skewed(FakeExchange):
        n = 0

        def handle(self, request):
            if request.url.path == "/api/v3/account" and Skewed.n == 0:
                Skewed.n += 1
                return httpx.Response(400, json={"code": -1021, "msg": "Timestamp outside of the recvWindow."})
            return super().handle(request)

    ex = Skewed()
    assert broker(ex)._request("GET", "/api/v3/account", signed=True)["balances"]
    assert len(ex.sent("GET", "/api/v3/time")) == 1 and all(check_signature({"raw": r["raw"]}) for r in ex.sent("GET", "/api/v3/account"))


# ------------------------------------------------------------------ end to end through the service: gate, approval, exchange


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "config").mkdir(parents=True)
    (h / "config" / "limits.toml").write_text('profile = "minimal"\nmax_exposure_fraction = 0.2\naccount_drawdown_halt = 0.15\ndaily_loss_halt = 0.025\n')
    monkeypatch.setenv("GETRICH_HOME", str(h))
    L.pin()


def test_the_gate_uses_the_testnets_own_price_and_the_exchange_filters(pinned):
    ex = FakeExchange(price=60000.0, fee_asset="USDT")
    b = broker(ex)
    oid, v = service.propose(OrderIntent("BTCUSDT", "buy", stop_price=57000.0), broker=b)          # no stored mainnet bars at all
    assert v["approved"] and v["qty"] == pytest.approx(0.00083)
    assert book.get_order(oid)["venue"] == "testnet" and not ex.sent("POST", "/api/v3/order")      # a proposal sends nothing to the exchange
    res = service.approve(oid, broker=b)
    assert res["ok"] and len(ex.sent("POST", "/api/v3/order")) == 2                                # market buy + protective stop
    assert book.load_state(["BTCUSDT"], venue="testnet").positions["BTCUSDT"].stop_price == 57000.0


def test_approving_for_the_wrong_venue_is_refused(pinned):
    from getrich.trading.sim import SimBroker

    oid, _ = service.propose(OrderIntent("BTCUSDT", "buy", stop_price=57000.0), broker=broker(FakeExchange()))
    out = service.approve(oid, broker=SimBroker())
    assert not out["ok"] and "venue" in out["note"]


def test_a_failed_protective_stop_leaves_the_book_flat(pinned):
    ex = FakeExchange(fail={"POST /api/v3/order": {"status": 400, "code": -1013, "msg": "x"}})
    b = broker(ex)
    oid, _ = service.propose(OrderIntent("BTCUSDT", "buy", stop_price=57000.0), broker=b)
    assert not service.approve(oid, broker=b)["ok"] and book.load_state(["BTCUSDT"], venue="testnet").positions == {}
