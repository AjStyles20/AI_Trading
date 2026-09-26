from __future__ import annotations

from collections import defaultdict
from threading import Lock
from uuid import uuid4

from .base import BrokerClient, BrokerExecutionResult, BrokerOrder
from database.sqlite_manager import clear_risk_equity_state, get_paper_account_state, save_paper_account_state


class PaperBroker(BrokerClient):
    broker_id = "paper"
    display_name = "Paper Broker"
    supports_live = False

    def __init__(self, starting_cash: float = 100000.0):
        self.starting_cash = float(starting_cash)
        self.cash = float(starting_cash)
        self.positions: dict[str, float] = defaultdict(float)
        self.last_prices: dict[str, float] = {}
        self._lock = Lock()
        self._restore()

    def _snapshot(self) -> dict:
        return {
            "starting_cash": self.starting_cash,
            "cash": self.cash,
            "positions": dict(self.positions),
            "last_prices": dict(self.last_prices),
        }

    def _restore(self) -> None:
        state = get_paper_account_state()
        if not state:
            save_paper_account_state(self._snapshot())
            return
        self.starting_cash = float(state.get("starting_cash", self.starting_cash))
        self.cash = float(state.get("cash", self.starting_cash))
        self.positions = defaultdict(float, {str(k): float(v) for k, v in (state.get("positions") or {}).items()})
        self.last_prices = {str(k): float(v) for k, v in (state.get("last_prices") or {}).items()}

    def reset(self) -> None:
        with self._lock:
            self.cash = self.starting_cash
            self.positions.clear()
            self.last_prices.clear()
            save_paper_account_state(self._snapshot())
            clear_risk_equity_state(self.broker_id, "paper")

    def get_account_summary(self, settings: dict, execution_mode: str) -> dict:
        with self._lock:
            market_value = sum(
                qty * self.last_prices.get(symbol, 0.0)
                for symbol, qty in self.positions.items()
            )
            return {
                "broker_id": self.broker_id,
                "display_name": self.display_name,
                "execution_mode": "paper",
                "configured": True,
                "can_trade": True,
                "cash": round(self.cash, 8),
                "market_value": round(market_value, 8),
                "equity": round(self.cash + market_value, 8),
                "balances": [{"asset": "USD", "free": round(self.cash, 8), "locked": 0.0}],
                "positions": [
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "last_price": self.last_prices.get(symbol, 0.0),
                        "market_value": qty * self.last_prices.get(symbol, 0.0),
                    }
                    for symbol, qty in self.positions.items()
                    if qty > 0
                ],
                "warnings": ["Paper broker uses simulated balances and immediate fills."],
            }

    def validate_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        side = order.side.upper()
        if side not in {"BUY", "SELL"}:
            return {"ok": False, "reason": "Paper broker supports BUY and SELL only.", "normalized_qty": 0.0}
        if order.qty <= 0 or order.price <= 0:
            return {"ok": False, "reason": "Quantity and price must be positive.", "normalized_qty": 0.0}
        with self._lock:
            if side == "BUY" and order.qty * order.price > self.cash + 1e-9:
                return {"ok": False, "reason": "Insufficient paper cash.", "normalized_qty": order.qty}
            if side == "SELL" and order.qty > self.positions.get(order.symbol, 0.0) + 1e-9:
                return {"ok": False, "reason": "Cannot sell more than the paper position.", "normalized_qty": order.qty}
        return {"ok": True, "reason": "Paper order validated.", "normalized_qty": float(order.qty)}

    def execute_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> BrokerExecutionResult:
        validation = self.validate_order(order, execution_mode, settings)
        if not validation["ok"]:
            return BrokerExecutionResult(
                broker_id=self.broker_id,
                execution_mode="paper",
                status="rejected",
                message=validation["reason"],
                filled_qty=0.0,
                filled_price=0.0,
                metadata=order.metadata,
            )

        side = order.side.upper()
        qty = float(validation["normalized_qty"])
        notional = qty * order.price
        with self._lock:
            if side == "BUY":
                self.cash -= notional
                self.positions[order.symbol] += qty
            else:
                self.cash += notional
                self.positions[order.symbol] -= qty
                if self.positions[order.symbol] <= 1e-12:
                    self.positions.pop(order.symbol, None)
            self.last_prices[order.symbol] = float(order.price)
            save_paper_account_state(self._snapshot())

        return BrokerExecutionResult(
            broker_id=self.broker_id,
            execution_mode="paper",
            status="filled",
            message=f"Paper-filled {side} {qty} {order.symbol} @ {order.price}",
            filled_qty=qty,
            filled_price=order.price,
            metadata={**(order.metadata or {}), "notional": notional, "paper_order_id": f"paper-{uuid4().hex[:16]}"},
        )
