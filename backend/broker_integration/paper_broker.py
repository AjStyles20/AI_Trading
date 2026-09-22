from __future__ import annotations

from .base import BrokerClient, BrokerExecutionResult, BrokerOrder


class PaperBroker(BrokerClient):
    broker_id = "paper"
    display_name = "Paper Broker"
    supports_live = False

    def get_account_summary(self, settings: dict, execution_mode: str) -> dict:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "execution_mode": "paper",
            "configured": True,
            "can_trade": True,
            "balances": [
                {"asset": "USD", "free": 100000.0, "locked": 0.0},
            ],
            "warnings": ["Paper broker uses simulated balances only."],
        }

    def execute_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> BrokerExecutionResult:
        return BrokerExecutionResult(
            broker_id=self.broker_id,
            execution_mode="paper",
            status="filled",
            message=f"Paper-filled {order.side} {order.qty} {order.symbol} @ {order.price}",
            filled_qty=order.qty,
            filled_price=order.price,
            metadata=order.metadata,
        )
