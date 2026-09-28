from backend.broker_integration.alpaca_broker import AlpacaBroker
from backend.broker_integration.binance_broker import BinanceBroker
from backend.broker_integration.bitget_broker import BitgetBroker
from backend.broker_integration.base import BrokerOrder


CLIENT_ID = "astral-0123456789abcdef01234567"


def _order(symbol, asset_type):
    return BrokerOrder(symbol, "BUY", 1.0, 100.0, asset_type, {"client_order_id": CLIENT_ID})


def _intent(symbol):
    return {
        "symbol": symbol, "qty": 1.0, "execution_mode": "live",
        "order_status": "submission_pending", "broker_order_id": None,
        "metadata": {"client_order_id": CLIENT_ID},
    }


def test_binance_submits_and_recovers_by_client_order_id(monkeypatch):
    broker = BinanceBroker()
    calls = []
    monkeypatch.setattr(broker, "is_configured", lambda settings: True)
    monkeypatch.setattr(broker, "validate_order", lambda *a: {"normalized_qty": 1.0})

    def request(method, path, payload, settings):
        calls.append((method, path, payload))
        if method == "POST":
            return {"orderId": 17, "status": "NEW", "executedQty": "0"}
        return {"orderId": 17, "status": "FILLED", "origQty": "1", "executedQty": "1", "cummulativeQuoteQty": "101"}

    monkeypatch.setattr(broker, "_signed_request", request)
    broker.execute_order(_order("BTC/USDT", "crypto"), "live", {})
    result = broker.get_order_status(_intent("BTC/USDT"), {})
    assert calls[0][2]["newClientOrderId"] == CLIENT_ID
    assert calls[1][2]["origClientOrderId"] == CLIENT_ID
    assert result["broker_order_id"] == "17"
    assert result["filled_qty"] == 1.0


def test_alpaca_submits_and_recovers_by_client_order_id(monkeypatch):
    broker = AlpacaBroker()
    calls = []
    monkeypatch.setattr(broker, "validate_order", lambda *a: {"normalized_qty": 1.0})

    def request(method, path, settings, execution_mode, **kwargs):
        calls.append((method, path, kwargs))
        return {"id": "a-17", "status": "filled", "qty": "1", "filled_qty": "1", "filled_avg_price": "101"}

    monkeypatch.setattr(broker, "_request", request)
    broker.execute_order(_order("AAPL", "stock"), "paper", {})
    result = broker.get_order_status(_intent("AAPL"), {})
    assert calls[0][2]["body"]["client_order_id"] == CLIENT_ID
    assert calls[1][1] == f"/v2/orders:by_client_order_id?client_order_id={CLIENT_ID}"
    assert result["broker_order_id"] == "a-17"


def test_bitget_submits_and_recovers_by_client_order_id(monkeypatch):
    broker = BitgetBroker()
    calls = []
    monkeypatch.setattr(broker, "validate_order", lambda *a: {"normalized_qty": 1.0})

    def request(method, path, settings, **kwargs):
        calls.append((method, path, kwargs))
        if method == "POST":
            return {"orderId": "b-17"}
        return {"orderId": "b-17", "status": "filled", "size": "1", "baseVolume": "1", "priceAvg": "101"}

    monkeypatch.setattr(broker, "_request", request)
    broker.execute_order(_order("BTC/USDT", "crypto"), "live", {})
    result = broker.get_order_status(_intent("BTC/USDT"), {})
    assert calls[0][2]["body"]["clientOid"] == CLIENT_ID
    assert calls[1][2]["params"] == {"clientOid": CLIENT_ID}
    assert result["broker_order_id"] == "b-17"
