"""Bitget order placement: limit-IOC buys sized in the base coin, unified orders in demo only."""
import io
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import backend.trading_api as trading_api
from backend.broker_integration import bitget_broker
from backend.broker_integration.base import BrokerOrder
from backend.broker_integration.bitget_broker import BitgetBroker

KEYS = {"bitget_demo_key": "demo-key", "bitget_demo_secret": "demo-secret", "bitget_demo_passphrase": "demo-pass"}
CLASSIC_DEMO = {"bitget_environment": "demo", "bitget_account_type": "classic", "api_keys": KEYS}
UNIFIED_DEMO = {"bitget_environment": "demo", "bitget_account_type": "unified", "api_keys": KEYS}

RULES = {"symbol": "BTCUSDT", "status": "online", "quantityPrecision": "6", "pricePrecision": "2",
         "minTradeUSDT": "1", "minOrderAmount": "1", "buyLimitPriceRatio": "0.02"}


@pytest.fixture
def bitget_api(monkeypatch):
    """Answers Bitget requests from `routes` and records each one as (path, query, body)."""
    calls = []
    routes = {
        "/api/v2/spot/public/symbols": [RULES],
        "/api/v3/market/instruments": [RULES],
        "/api/v2/spot/trade/place-order": {"orderId": "333"},
        "/api/v3/trade/place-order": {"orderId": "222"},
        "/api/v3/trade/order-info": {"orderId": "222", "orderStatus": "filled", "qty": "0.001",
                                     "cumExecQty": "0.001", "avgPrice": "80100.5"},
        "/api/v3/trade/cancel-order": {"orderId": "222"},
    }

    def fake_urlopen(request, timeout=None):
        url = urlparse(request.full_url)
        headers = {key.lower(): value for key, value in request.header_items()}
        calls.append(SimpleNamespace(
            path=url.path, query=parse_qs(url.query), headers=headers,
            body=json.loads(request.data) if request.data else None,
        ))
        return io.BytesIO(json.dumps({"code": "00000", "data": routes[url.path]}).encode())

    monkeypatch.setattr(bitget_broker, "resolve_api_keys", lambda settings: dict(settings.get("api_keys", {})))
    monkeypatch.setattr(bitget_broker.urllib.request, "urlopen", fake_urlopen)
    return SimpleNamespace(calls=calls, routes=routes)


def order(side="BUY", qty=0.0012345, price=80_000.0):
    return BrokerOrder(symbol="BTC/USDT", side=side, qty=qty, price=price, asset_type="crypto",
                       metadata={"client_order_id": "astral-1"})


def placed(bitget_api):
    return [call for call in bitget_api.calls if call.path.endswith("place-order")]


def test_classic_buy_is_a_limit_ioc_sized_in_the_base_coin(bitget_api):
    result = BitgetBroker().execute_order(order(), "live", CLASSIC_DEMO)

    [call] = placed(bitget_api)
    assert call.path == "/api/v2/spot/trade/place-order"
    assert call.headers["paptrading"] == "1"
    # Quantity rounded down to 6 decimals; price capped 0.5% above the quote, rounded up.
    assert call.body == {"symbol": "BTCUSDT", "side": "buy", "size": "0.001234", "clientOid": "astral-1",
                         "orderType": "limit", "price": "80400.00", "force": "ioc"}
    assert result.status == "submitted" and result.filled_qty == 0
    assert result.metadata["broker_order_id"] == "333"
    assert result.metadata["order_type"] == "limit_ioc"


def test_classic_sell_is_a_market_order_in_the_base_coin(bitget_api):
    BitgetBroker().execute_order(order("SELL"), "live", CLASSIC_DEMO)

    [call] = placed(bitget_api)
    assert call.body == {"symbol": "BTCUSDT", "side": "sell", "size": "0.001234", "clientOid": "astral-1",
                         "orderType": "market"}


def test_unified_demo_buy_uses_the_v3_order_endpoint(bitget_api):
    result = BitgetBroker().execute_order(order(), "live", UNIFIED_DEMO)

    assert bitget_api.calls[0].path == "/api/v3/market/instruments"
    [call] = placed(bitget_api)
    assert call.path == "/api/v3/trade/place-order"
    assert call.headers["paptrading"] == "1"
    assert call.headers["access-key"] == "demo-key"
    assert call.body == {"category": "SPOT", "symbol": "BTCUSDT", "side": "buy", "qty": "0.001234",
                         "clientOid": "astral-1", "orderType": "limit", "price": "80400.00", "timeInForce": "ioc"}
    assert result.metadata["broker_order_id"] == "222"
    assert result.metadata["account_type"] == "unified"


def test_unified_demo_sell_is_a_market_order(bitget_api):
    BitgetBroker().execute_order(order("SELL"), "live", UNIFIED_DEMO)

    [call] = placed(bitget_api)
    assert call.body == {"category": "SPOT", "symbol": "BTCUSDT", "side": "sell", "qty": "0.001234",
                         "clientOid": "astral-1", "orderType": "market"}


def test_validation_reports_the_rounded_quantity_and_buy_cap(bitget_api):
    validation = BitgetBroker().validate_order(order(), "live", CLASSIC_DEMO)

    assert validation["normalized_qty"] == 0.001234
    assert validation["original_qty"] == 0.0012345
    assert validation["limit_price"] == 80400.0
    assert validation["max_notional"] == pytest.approx(0.001234 * 80400.0)
    assert placed(bitget_api) == []


@pytest.mark.parametrize(("rules", "qty", "message"), [
    ({}, 0.0000004, "rounds to zero"),
    ({}, 0.00001, "below Bitget's minimum"),
    ({"status": "offline"}, 0.001, "not trading BTCUSDT"),
    ({"buyLimitPriceRatio": "0.001"}, 0.001, "allowed range"),
])
def test_orders_bitget_would_refuse_are_stopped_before_submission(bitget_api, rules, qty, message):
    bitget_api.routes["/api/v2/spot/public/symbols"] = [{**RULES, **rules}]

    with pytest.raises(ValueError, match=message):
        BitgetBroker().execute_order(order(qty=qty), "live", CLASSIC_DEMO)
    assert placed(bitget_api) == []


def test_missing_symbol_rules_block_the_order(bitget_api):
    bitget_api.routes["/api/v3/market/instruments"] = []

    with pytest.raises(ValueError, match="no spot symbol rules"):
        BitgetBroker().validate_order(order(), "live", UNIFIED_DEMO)


def test_symbol_rules_are_cached(bitget_api):
    broker = BitgetBroker()
    broker.validate_order(order(), "live", CLASSIC_DEMO)
    broker.validate_order(order(), "live", CLASSIC_DEMO)

    assert [call.path for call in bitget_api.calls] == ["/api/v2/spot/public/symbols"]


def test_unified_order_status_maps_the_confirmed_fill(bitget_api):
    status = BitgetBroker().get_order_status({"broker_order_id": "222", "qty": 0.001, "metadata": {}}, UNIFIED_DEMO)

    assert bitget_api.calls[0].query == {"orderId": ["222"]}
    assert status["order_status"] == "filled"
    assert status["filled_qty"] == 0.001
    assert status["filled_price"] == 80100.5
    assert status["metadata"]["fill_progress_pct"] == pytest.approx(100)


def test_unified_order_status_falls_back_to_the_client_order_id(bitget_api):
    bitget_api.routes["/api/v3/trade/order-info"] = {"orderId": "222", "orderStatus": "cancelled", "qty": "0.001",
                                                     "cumExecQty": "0", "avgPrice": "0"}
    status = BitgetBroker().get_order_status({"broker_order_id": None, "metadata": {"client_order_id": "astral-1"}},
                                             UNIFIED_DEMO)

    assert bitget_api.calls[0].query == {"clientOid": ["astral-1"]}
    assert status["order_status"] == "cancelled"
    assert status["broker_order_id"] == "222"
    assert status["filled_qty"] == 0 and status["filled_price"] == 0


def test_unified_order_without_a_status_stays_unresolved(bitget_api):
    bitget_api.routes["/api/v3/trade/order-info"] = {}

    with pytest.raises(ValueError, match="stays unresolved"):
        BitgetBroker().get_order_status({"broker_order_id": "222", "metadata": {}}, UNIFIED_DEMO)


def test_unified_cancel_is_only_a_request_until_reconciled(bitget_api):
    result = BitgetBroker().cancel_order({"broker_order_id": "222", "filled_qty": 0, "metadata": {}}, UNIFIED_DEMO)

    [call] = bitget_api.calls
    assert call.path == "/api/v3/trade/cancel-order"
    assert call.body == {"category": "SPOT", "orderId": "222"}
    assert result["order_status"] == "cancel_requested"


def test_classic_cancel_is_still_refused(bitget_api):
    with pytest.raises(ValueError, match="classic accounts"):
        BitgetBroker().cancel_order({"broker_order_id": "333", "metadata": {}}, CLASSIC_DEMO)
    assert bitget_api.calls == []


def test_guarded_submission_places_one_unified_demo_order(bitget_api, monkeypatch):
    recorded, updates = [], []
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": False})
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: SimpleNamespace(approved=True, reasons=[]))
    monkeypatch.setattr(trading_api, "record_trade", lambda *args, **kwargs: recorded.append((args, kwargs)) or 7)
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *args, **kwargs: updates.append((args, kwargs)))

    result = trading_api.submit_guarded_order(
        broker=BitgetBroker(), order=order(), settings=UNIFIED_DEMO, execution_mode="live",
        broker_id="bitget", account_equity=100_000.0, current_position_qty=0.0,
        day_start_equity=100_000.0, peak_equity=100_000.0,
    )

    # The intent is recorded with the rounded quantity before Bitget is called.
    [(args, kwargs)] = recorded
    assert args[2] == 0.001234 and kwargs["order_status"] == "submission_pending"
    [call] = placed(bitget_api)
    assert call.body["qty"] == "0.001234"
    assert call.body["clientOid"] == kwargs["metadata"]["client_order_id"]
    # Acceptance is not a fill: nothing is filled until reconciliation confirms it.
    [(update_args, update_kwargs)] = updates
    assert update_args[:3] == (7, "submitted", "222")
    assert update_kwargs["filled_qty"] == 0
    assert result.status == "submitted"
