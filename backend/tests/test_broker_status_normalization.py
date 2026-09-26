import pytest

from backend.broker_integration.binance_broker import BinanceBroker
from backend.broker_integration.bitget_broker import BitgetBroker


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
