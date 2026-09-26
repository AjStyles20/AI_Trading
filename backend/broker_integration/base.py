from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class BrokerOrder:
    symbol: str
    side: str
    qty: float
    price: float
    asset_type: str
    metadata: Dict[str, Any]


@dataclass
class BrokerExecutionResult:
    broker_id: str
    execution_mode: str
    status: str
    message: str
    filled_qty: float
    filled_price: float
    metadata: Dict[str, Any]


class BrokerClient(ABC):
    broker_id: str = "paper"
    display_name: str = "Paper Broker"
    supports_live: bool = False
    supported_asset_types: tuple[str, ...] = ("crypto", "stock")

    def get_capabilities(self) -> Dict[str, Any]:
        """Declare venue features without leaking broker-specific behavior upstream."""
        return {
            "asset_types": list(self.supported_asset_types),
            "live_trading": self.supports_live,
            "market_orders": True,
            "order_status": True,
            "open_orders": True,
            "positions": True,
            "cancellation": self.__class__.cancel_order is not BrokerClient.cancel_order,
            "streaming_order_updates": False,
            "fractional_quantity": None,
        }

    def get_status(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "supports_live": self.supports_live,
            "supported_asset_types": list(self.supported_asset_types),
            "configured": self.is_configured(settings),
            "environment": "paper" if self.broker_id == "paper" else "live",
            "capabilities": self.get_capabilities(),
        }

    def is_configured(self, settings: Dict[str, Any]) -> bool:
        return True

    def get_account_summary(self, settings: Dict[str, Any], execution_mode: str) -> Dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "execution_mode": execution_mode,
            "configured": self.is_configured(settings),
            "can_trade": execution_mode == "paper" or self.supports_live,
            "balances": [],
            "warnings": [],
        }

    def validate_order(self, order: BrokerOrder, execution_mode: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": True,
            "warnings": [],
            "normalized_qty": order.qty,
            "original_qty": order.qty,
            "estimated_notional": order.qty * order.price,
        }

    def test_order(self, order: BrokerOrder, execution_mode: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        validation = self.validate_order(order, execution_mode, settings)
        return {
            "ok": True,
            "broker_id": self.broker_id,
            "execution_mode": execution_mode,
            "message": f"{self.display_name} test order validated successfully.",
            "validation": validation,
        }

    def get_order_status(self, trade: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "order_status": trade.get("order_status", "unknown"),
            "broker_order_id": trade.get("broker_order_id"),
            "metadata": trade.get("metadata", {}),
        }

    def cancel_order(self, trade: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        raise ValueError(f"{self.display_name} does not support broker-side order cancellation.")

    def list_open_orders(self, symbol: str, asset_type: str, settings: Dict[str, Any], execution_mode: str) -> list[Dict[str, Any]]:
        return []

    def list_positions(self, symbol: str, asset_type: str, settings: Dict[str, Any], execution_mode: str) -> list[Dict[str, Any]]:
        return []

    @abstractmethod
    def execute_order(self, order: BrokerOrder, execution_mode: str, settings: Dict[str, Any]) -> BrokerExecutionResult:
        raise NotImplementedError
