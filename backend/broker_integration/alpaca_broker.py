from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .base import BrokerClient, BrokerExecutionResult, BrokerOrder


class AlpacaBroker(BrokerClient):
    broker_id = "alpaca"
    display_name = "Alpaca"
    supports_live = True
    supported_asset_types = ("stock",)

    def _get_api_keys(self, settings: dict) -> dict:
        return settings.get("api_keys", {}) if settings else {}

    def _get_base_url(self, execution_mode: str) -> str:
        if execution_mode == "paper":
            return "https://paper-api.alpaca.markets"
        return "https://api.alpaca.markets"

    def _get_environment_label(self, execution_mode: str) -> str:
        return "paper" if execution_mode == "paper" else "live"

    def _get_credentials(self, settings: dict, execution_mode: str) -> tuple[str, str]:
        api_keys = self._get_api_keys(settings)
        if execution_mode == "paper":
            api_key = api_keys.get("alpaca_paper_key") or api_keys.get("alpaca_key", "")
            api_secret = api_keys.get("alpaca_paper_secret") or api_keys.get("alpaca_secret", "")
            if not api_key or not api_secret:
                raise ValueError(
                    "Alpaca paper trading requires alpaca_paper_key/alpaca_paper_secret or alpaca_key/alpaca_secret."
                )
            return api_key, api_secret

        api_key = api_keys.get("alpaca_key", "")
        api_secret = api_keys.get("alpaca_secret", "")
        if not api_key or not api_secret:
            raise ValueError("Alpaca live trading requires alpaca_key and alpaca_secret in settings.")
        return api_key, api_secret

    def _request(
        self,
        method: str,
        path: str,
        settings: dict,
        execution_mode: str,
        params: dict[str, str | int | float] | None = None,
        body: dict | None = None,
    ) -> dict | list:
        api_key, api_secret = self._get_credentials(settings, execution_mode)
        base_url = self._get_base_url(execution_mode)
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}{path}{query}",
            method=method.upper(),
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
                "Content-Type": "application/json",
            },
            data=payload,
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Alpaca API error ({exc.code}): {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Alpaca network error: {exc.reason}") from exc

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.replace("/", "").upper()

    def _extract_broker_order_id(self, response: dict) -> str | None:
        order_id = response.get("id")
        if not order_id:
            return None
        return str(order_id)

    def get_status(self, settings: dict) -> dict:
        api_keys = self._get_api_keys(settings)
        configured = bool(
            (api_keys.get("alpaca_key") and api_keys.get("alpaca_secret"))
            or (api_keys.get("alpaca_paper_key") and api_keys.get("alpaca_paper_secret"))
        )
        status = super().get_status(settings)
        status["configured"] = configured
        status["environment"] = "dual"
        return status

    def is_configured(self, settings: dict) -> bool:
        api_keys = self._get_api_keys(settings)
        return bool(api_keys.get("alpaca_key") and api_keys.get("alpaca_secret"))

    def get_account_summary(self, settings: dict, execution_mode: str) -> dict:
        account = self._request("GET", "/v2/account", settings, execution_mode)
        if not isinstance(account, dict):
            raise ValueError("Unexpected Alpaca account response.")

        balances = [
            {"asset": "USD", "free": float(account.get("cash", 0) or 0), "locked": 0.0},
            {"asset": "Buying Power", "free": float(account.get("buying_power", 0) or 0), "locked": 0.0},
            {"asset": "Portfolio Value", "free": float(account.get("portfolio_value", 0) or 0), "locked": 0.0},
        ]
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "execution_mode": execution_mode,
            "environment": self._get_environment_label(execution_mode),
            "configured": True,
            "can_trade": str(account.get("trading_blocked", "false")).lower() not in {"true", "1"},
            "balances": balances,
            "warnings": [],
        }

    def validate_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        self._get_credentials(settings, execution_mode)
        return {
            "ok": True,
            "warnings": [],
            "normalized_qty": order.qty,
            "original_qty": order.qty,
            "estimated_notional": order.qty * order.price,
        }

    def execute_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> BrokerExecutionResult:
        validation = self.validate_order(order, execution_mode, settings)
        qty = float(validation.get("normalized_qty", order.qty))
        payload = {
            "symbol": self._normalize_symbol(order.symbol),
            "side": order.side.lower(),
            "type": "market",
            "qty": qty,
            "time_in_force": "day",
        }
        response = self._request("POST", "/v2/orders", settings, execution_mode, body=payload)
        if not isinstance(response, dict):
            raise ValueError("Unexpected Alpaca order response.")

        status = str(response.get("status", "accepted")).lower()
        filled_qty = float(response.get("filled_qty", 0) or 0)
        filled_avg_price = float(response.get("filled_avg_price", order.price) or order.price)
        return BrokerExecutionResult(
            broker_id=self.broker_id,
            execution_mode=execution_mode,
            status=status,
            message=f"Alpaca {execution_mode} order {status}: {order.side.upper()} {qty} {order.symbol}",
            filled_qty=filled_qty if filled_qty > 0 else qty,
            filled_price=filled_avg_price,
            metadata={
                **response,
                "order_status": status,
                "broker_order_id": self._extract_broker_order_id(response),
                "requested_qty": order.qty,
                "normalized_qty": qty,
            },
        )

    def test_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        validation = self.validate_order(order, execution_mode, settings)
        return {
            "ok": True,
            "broker_id": self.broker_id,
            "execution_mode": execution_mode,
            "message": f"Alpaca {execution_mode} order validated successfully.",
            "validation": validation,
            "environment": self._get_environment_label(execution_mode),
        }

    def get_order_status(self, trade: dict, settings: dict) -> dict:
        broker_order_id = trade.get("broker_order_id")
        if not broker_order_id:
            return super().get_order_status(trade, settings)

        response = self._request("GET", f"/v2/orders/{broker_order_id}", settings, trade.get("execution_mode", "live"))
        if not isinstance(response, dict):
            return super().get_order_status(trade, settings)
        status = str(response.get("status", trade.get("order_status", "unknown"))).lower()
        filled_qty = float(response.get("filled_qty", 0) or 0)
        original_qty = float(response.get("qty", trade.get("qty", 0)) or 0)
        return {
            "order_status": status,
            "broker_order_id": self._extract_broker_order_id(response) or broker_order_id,
            "metadata": {
                **response,
                "orig_qty": original_qty,
                "executed_qty": filled_qty,
                "fill_progress_pct": (filled_qty / original_qty * 100) if original_qty > 0 else 0,
                "broker_reason": response.get("status"),
            },
        }

    def cancel_order(self, trade: dict, settings: dict) -> dict:
        broker_order_id = trade.get("broker_order_id")
        if not broker_order_id:
            raise ValueError("This trade does not have a broker order id.")

        self._request("DELETE", f"/v2/orders/{broker_order_id}", settings, trade.get("execution_mode", "live"))
        return {
            "order_status": "canceled",
            "broker_order_id": broker_order_id,
            "metadata": {"broker_reason": "canceled"},
            "message": f"Alpaca order {broker_order_id} canceled.",
        }

    def list_open_orders(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        normalized_symbol = self._normalize_symbol(symbol) if symbol else ""
        params = {"status": "open", "direction": "desc"}
        if normalized_symbol:
            params["symbols"] = normalized_symbol
        response = self._request(
            "GET",
            "/v2/orders",
            settings,
            execution_mode,
            params=params,
        )
        if not isinstance(response, list):
            return []

        return [
            {
                "broker_order_id": self._extract_broker_order_id(order),
                "symbol": order.get("symbol", normalized_symbol),
                "side": str(order.get("side", "")).upper(),
                "status": str(order.get("status", "unknown")).lower(),
                "type": str(order.get("type", "market")).lower(),
                "orig_qty": float(order.get("qty", 0) or 0),
                "executed_qty": float(order.get("filled_qty", 0) or 0),
                "price": float(order.get("filled_avg_price", 0) or 0),
                "time": 0,
            }
            for order in response
        ]

    def list_positions(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        response = self._request("GET", "/v2/positions", settings, execution_mode)
        if not isinstance(response, list):
            return []

        normalized_symbol = self._normalize_symbol(symbol) if symbol else ""
        items: list[dict] = []
        for position in response:
            if normalized_symbol and position.get("symbol") != normalized_symbol:
                continue
            qty = float(position.get("qty", 0) or 0)
            if qty == 0:
                continue
            items.append(
                {
                    "symbol": position.get("symbol", normalized_symbol),
                    "qty": qty,
                    "available_qty": float(position.get("qty_available", qty) or qty),
                    "locked_qty": max(qty - float(position.get("qty_available", qty) or qty), 0),
                    "market_value": float(position.get("market_value", 0) or 0),
                    "avg_entry_price": float(position.get("avg_entry_price", 0) or 0),
                    "unrealized_pl": float(position.get("unrealized_pl", 0) or 0),
                    "side": str(position.get("side", "long")).lower(),
                }
            )
        return items
