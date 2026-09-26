import pytest

from backend.broker_integration.binance_broker import BinanceBroker
from backend.broker_integration.bitget_broker import BitgetBroker
from backend.broker_integration.alpaca_broker import AlpacaBroker


def test_binance_status_normalizes_partial_fill(monkeypatch):
    broker = BinanceBroker()
    response = {
        "orderId": 123,
        "status": "PARTIALLY_FILLED",
        "origQty": "2.0",
        "executedQty": "0.5",
        "cummulativeQuoteQty": "50.0",
    }
    monkeypatch.setattr(broker, "_signed_request", lambda *args, **kwargs: response)

    result = broker.get_order_status(
        {"broker_order_id": "123", "execution_mode": "live", "symbol": "BTC/USDT", "qty": 2.0},
        {},
    )

    assert result["order_status"] == "partially_filled"
    assert result["filled_qty"] == 0.5
    assert result["filled_price"] == 100.0
    assert result["metadata"]["fill_progress_pct"] == 25.0


def test_binance_status_does_not_invent_unfilled_price(monkeypatch):
    broker = BinanceBroker()
    response = {
        "orderId": 123,
        "status": "NEW",
        "origQty": "2.0",
        "executedQty": "0",
        "cummulativeQuoteQty": "0",
    }
    monkeypatch.setattr(broker, "_signed_request", lambda *args, **kwargs: response)

    result = broker.get_order_status(
        {"broker_order_id": "123", "execution_mode": "live", "symbol": "BTC/USDT", "qty": 2.0},
        {},
    )

    assert result["filled_qty"] == 0.0
    assert result["filled_price"] == 0.0


@pytest.mark.parametrize(
    ("price_avg", "price", "expected_price"),
    [("101.5", "99", 101.5), (None, "99", 99.0), (None, None, 0.0)],
)
def test_bitget_status_normalizes_fill_price(monkeypatch, price_avg, price, expected_price):
    broker = BitgetBroker()
    response = {
        "orderId": "abc",
        "status": "partially_filled",
        "size": "2.0",
        "baseVolume": "0.5",
        "priceAvg": price_avg,
        "price": price,
    }
    monkeypatch.setattr(broker, "_request", lambda *args, **kwargs: response)

    result = broker.get_order_status(
        {"broker_order_id": "abc", "execution_mode": "live", "symbol": "BTCUSDT", "qty": 2.0},
        {},
    )

    assert result["filled_qty"] == 0.5
    assert result["filled_price"] == expected_price
    assert result["metadata"]["fill_progress_pct"] == 25.0



def test_broker_capability_contract_is_normalized():
    from backend.broker_integration.base import BrokerClient, BrokerOrder, BrokerExecutionResult

    class MinimalBroker(BrokerClient):
        broker_id = "minimal"
        display_name = "Minimal"
        supports_live = True
        supported_asset_types = ("forex", "stock")

        def execute_order(self, order, execution_mode, settings):
            return BrokerExecutionResult(
                broker_id=self.broker_id,
                execution_mode=execution_mode,
                status="filled",
                message="ok",
                filled_qty=order.qty,
                filled_price=order.price,
                metadata={},
            )

    broker = MinimalBroker()
    capabilities = broker.get_capabilities()
    status = broker.get_status({})

    assert capabilities["asset_types"] == ["forex", "stock"]
    assert capabilities["live_trading"] is True
    assert capabilities["order_status"] is True
    assert capabilities["cancellation"] is False
    assert status["capabilities"] == capabilities



def test_alpaca_status_returns_cumulative_fill_state(monkeypatch):
    broker = AlpacaBroker()
    response = {
        "id": "alp-1",
        "status": "partially_filled",
        "qty": "4",
        "filled_qty": "1.5",
        "filled_avg_price": "205.25",
    }
    monkeypatch.setattr(broker, "_request", lambda *args, **kwargs: response)

    result = broker.get_order_status(
        {"broker_order_id": "alp-1", "execution_mode": "paper", "symbol": "AAPL", "qty": 4.0},
        {},
    )

    assert result["order_status"] == "partially_filled"
    assert result["filled_qty"] == 1.5
    assert result["filled_price"] == 205.25
    assert result["metadata"]["fill_progress_pct"] == 37.5


@pytest.mark.parametrize(
    ("broker_factory", "response", "trade", "expected_first", "expected_second"),
    [
        (
            BinanceBroker,
            {"orderId": 1, "status": "PARTIALLY_FILLED", "origQty": "2", "executedQty": "0.5", "cummulativeQuoteQty": "50"},
            {"broker_order_id": "1", "execution_mode": "live", "symbol": "BTC/USDT", "qty": 2.0},
            0.5, 1.25,
        ),
        (
            BitgetBroker,
            {"orderId": "b1", "status": "partially_filled", "size": "2", "baseVolume": "0.5", "priceAvg": "100"},
            {"broker_order_id": "b1", "execution_mode": "live", "symbol": "BTCUSDT", "qty": 2.0},
            0.5, 1.25,
        ),
        (
            AlpacaBroker,
            {"id": "a1", "status": "partially_filled", "qty": "2", "filled_qty": "0.5", "filled_avg_price": "100"},
            {"broker_order_id": "a1", "execution_mode": "paper", "symbol": "AAPL", "qty": 2.0},
            0.5, 1.25,
        ),
    ],
)
def test_broker_status_fill_quantity_is_cumulative(
    monkeypatch, broker_factory, response, trade, expected_first, expected_second
):
    broker = broker_factory()
    request_name = "_signed_request" if isinstance(broker, BinanceBroker) else "_request"
    current = dict(response)

    monkeypatch.setattr(broker, request_name, lambda *args, **kwargs: current)
    first = broker.get_order_status(trade, {})
    assert first["filled_qty"] == expected_first

    if isinstance(broker, BinanceBroker):
        current["executedQty"] = str(expected_second)
        current["cummulativeQuoteQty"] = str(expected_second * 100)
    elif isinstance(broker, BitgetBroker):
        current["baseVolume"] = str(expected_second)
    else:
        current["filled_qty"] = str(expected_second)

    second = broker.get_order_status(trade, {})
    assert second["filled_qty"] == expected_second
    assert second["filled_qty"] != expected_second - expected_first
