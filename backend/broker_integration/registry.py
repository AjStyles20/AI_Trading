from __future__ import annotations

from typing import Dict, List

from .alpaca_broker import AlpacaBroker
from .base import BrokerClient
from .bitget_broker import BitgetBroker
from .binance_broker import BinanceBroker
from .paper_broker import PaperBroker


class BrokerRegistry:
    def __init__(self) -> None:
        self._brokers: Dict[str, BrokerClient] = {
            "paper": PaperBroker(),
            "binance": BinanceBroker(),
            "bitget": BitgetBroker(),
            "alpaca": AlpacaBroker(),
        }

    def list_brokers(self, settings: dict) -> List[dict]:
        return [broker.get_status(settings) for broker in self._brokers.values()]

    def get(self, broker_id: str) -> BrokerClient:
        if broker_id not in self._brokers:
            raise ValueError(f"Unsupported broker: {broker_id}")
        return self._brokers[broker_id]


broker_registry = BrokerRegistry()
