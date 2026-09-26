from __future__ import annotations

from typing import Dict, List

from .alpaca_broker import AlpacaBroker
from .base import BrokerClient
from .bitget_broker import BitgetBroker
from .binance_broker import BinanceBroker
from .paper_broker import PaperBroker


class BrokerRegistry:
    def __init__(self) -> None:
        # Delay broker construction until first use. In particular, PaperBroker
        # restores persisted state and must not touch SQLite during module import.
        self._brokers: Dict[str, BrokerClient] = {}

    def _ensure_brokers(self) -> None:
        if self._brokers:
            return
        self._brokers = {
            "paper": PaperBroker(),
            "binance": BinanceBroker(),
            "bitget": BitgetBroker(),
            "alpaca": AlpacaBroker(),
        }

    def list_brokers(self, settings: dict) -> List[dict]:
        self._ensure_brokers()
        return [broker.get_status(settings) for broker in self._brokers.values()]

    def get(self, broker_id: str) -> BrokerClient:
        self._ensure_brokers()
        if broker_id not in self._brokers:
            raise ValueError(f"Unsupported broker: {broker_id}")
        return self._brokers[broker_id]


broker_registry = BrokerRegistry()
