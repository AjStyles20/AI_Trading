import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.broker_integration.alpaca_broker import AlpacaBroker
from backend.broker_integration.base import BrokerOrder


@pytest.mark.parametrize(
    ("status", "filled_qty", "filled_avg_price", "expected_qty", "expected_price"),
    [
        ("accepted", "0", None, 0.0, 0.0),
        ("partially_filled", "0.4", "101.25", 0.4, 101.25),
        ("filled", "1.0", "102.50", 1.0, 102.50),
    ],
)
def test_alpaca_execution_preserves_fill_truth(
    monkeypatch, status, filled_qty, filled_avg_price, expected_qty, expected_price
):
    broker = AlpacaBroker()
    monkeypatch.setattr(
        broker,
        "validate_order",
        lambda order, execution_mode, settings: {
            "ok": True,
            "normalized_qty": order.qty,
        },
    )
    monkeypatch.setattr(
        broker,
        "_request",
        lambda *args, **kwargs: {
            "id": "order-123",
            "status": status,
            "filled_qty": filled_qty,
            "filled_avg_price": filled_avg_price,
        },
    )

    result = broker.execute_order(
        BrokerOrder(
            symbol="AAPL",
            side="BUY",
            qty=1.0,
            price=100.0,
            asset_type="stock",
            metadata={},
        ),
        "paper",
        {},
    )

    assert result.status == status
    assert result.filled_qty == expected_qty
    assert result.filled_price == expected_price
    assert result.metadata["broker_order_id"] == "order-123"


def test_alpaca_cancel_requires_reconciliation(monkeypatch):
    broker = AlpacaBroker()
    calls = []

    def fake_request(method, path, settings, execution_mode, **kwargs):
        calls.append((method, path, execution_mode))
        return None

    monkeypatch.setattr(broker, "_request", fake_request)
    trade = {
        "broker_order_id": "order-123",
        "execution_mode": "live",
        "filled_qty": 0.4,
    }

    result = broker.cancel_order(trade, {})

    assert calls == [("DELETE", "/v2/orders/order-123", "live")]
    assert result["order_status"] == "cancel_requested"
    assert result["broker_order_id"] == "order-123"
    assert result["metadata"]["executed_qty"] == 0.4
    assert "reconciliation" in result["message"].lower()
