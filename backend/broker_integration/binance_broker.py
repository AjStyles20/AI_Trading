from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_DOWN

from .base import BrokerClient, BrokerExecutionResult, BrokerOrder
from core.credential_provider import resolve_api_keys


class BinanceBroker(BrokerClient):
    broker_id = "binance"
    display_name = "Binance"
    supports_live = True
    supported_asset_types = ("crypto",)

    def _get_api_keys(self, settings: dict) -> dict:
        return resolve_api_keys(settings)

    def _use_testnet(self, settings: dict) -> bool:
        api_keys = self._get_api_keys(settings)
        return str(api_keys.get("binance_testnet", "")).strip().lower() in {"1", "true", "yes", "on"}

    def _get_base_url(self, settings: dict) -> str:
        if self._use_testnet(settings):
            return "https://testnet.binance.vision"
        return "https://api.binance.com"

    def _get_environment_label(self, settings: dict) -> str:
        return "testnet" if self._use_testnet(settings) else "live"

    def get_status(self, settings: dict) -> dict:
        status = super().get_status(settings)
        status["environment"] = self._get_environment_label(settings)
        return status

    def _extract_broker_order_id(self, response: dict) -> str | None:
        order_id = response.get("orderId")
        if order_id is None:
            return None
        return str(order_id)

    def is_configured(self, settings: dict) -> bool:
        api_keys = self._get_api_keys(settings)
        if self._use_testnet(settings):
            return bool(api_keys.get("binance_testnet_key") and api_keys.get("binance_testnet_secret"))
        return bool(api_keys.get("binance_key") and api_keys.get("binance_secret"))

    def _get_credentials(self, settings: dict) -> tuple[str, str]:
        api_keys = self._get_api_keys(settings)
        if self._use_testnet(settings):
            api_key = api_keys.get("binance_testnet_key", "")
            api_secret = api_keys.get("binance_testnet_secret", "")
            if not api_key or not api_secret:
                raise ValueError(
                    "Binance testnet requires binance_testnet_key and binance_testnet_secret in settings."
                )
            return api_key, api_secret

        api_key = api_keys.get("binance_key", "")
        api_secret = api_keys.get("binance_secret", "")
        if not api_key or not api_secret:
            raise ValueError("Binance live trading requires binance_key and binance_secret in settings.")
        return api_key, api_secret

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    def _get_symbol_info(self, symbol: str, settings: dict) -> dict:
        exchange_info = self._public_request("/api/v3/exchangeInfo", settings, {"symbol": symbol})
        symbols = exchange_info.get("symbols", [])
        if not symbols:
            raise ValueError(f"Binance symbol not found: {symbol}")
        return symbols[0]

    def _normalize_quantity(self, qty: float, step_size: float) -> float:
        if step_size <= 0:
            return qty
        qty_decimal = Decimal(str(qty))
        step_decimal = Decimal(str(step_size))
        normalized = (qty_decimal / step_decimal).to_integral_value(rounding=ROUND_DOWN) * step_decimal
        return float(normalized)

    def _signed_request(
        self,
        method: str,
        path: str,
        params: dict[str, str | int | float],
        settings: dict,
    ) -> dict:
        api_key, api_secret = self._get_credentials(settings)
        base_url = self._get_base_url(settings)
        query_params = {**params, "timestamp": int(time.time() * 1000)}
        query_string = urllib.parse.urlencode(query_params)
        signature = hmac.new(
            api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request_url = f"{base_url}{path}?{query_string}&signature={signature}"
        request = urllib.request.Request(
            request_url,
            method=method.upper(),
            headers={"X-MBX-APIKEY": api_key},
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Binance API error ({exc.code}): {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Binance network error: {exc.reason}") from exc

    def _public_request(
        self,
        path: str,
        settings: dict,
        params: dict[str, str | int | float] | None = None,
    ) -> dict:
        base_url = self._get_base_url(settings)
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        request = urllib.request.Request(f"{base_url}{path}{query}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Binance API error ({exc.code}): {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Binance network error: {exc.reason}") from exc

    def get_account_summary(self, settings: dict, execution_mode: str) -> dict:
        if execution_mode == "paper":
            return {
                "broker_id": self.broker_id,
                "display_name": self.display_name,
                "execution_mode": "paper",
                "environment": "simulated",
                "configured": self.is_configured(settings),
                "can_trade": True,
                "balances": [{"asset": "USDT", "free": 10000.0, "locked": 0.0}],
                "warnings": ["Binance paper mode uses simulated balances."],
            }

        account = self._signed_request("GET", "/api/v3/account", {}, settings)
        balances = [
            {
                "asset": balance.get("asset", ""),
                "free": float(balance.get("free", 0)),
                "locked": float(balance.get("locked", 0)),
            }
            for balance in account.get("balances", [])
            if float(balance.get("free", 0)) > 0 or float(balance.get("locked", 0)) > 0
        ][:10]

        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "execution_mode": "live",
            "environment": self._get_environment_label(settings),
            "configured": True,
            "can_trade": bool(account.get("canTrade", False)),
            "balances": balances,
            "warnings": ["Binance testnet is enabled."] if self._use_testnet(settings) else [],
        }

    def validate_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        if execution_mode == "paper":
            return {"ok": True, "warnings": []}

        symbol = self._normalize_symbol(order.symbol)
        symbol_info = self._get_symbol_info(symbol, settings)
        if symbol_info.get("status") != "TRADING":
            raise ValueError(f"Binance symbol is not tradable right now: {symbol}")

        filters = {entry.get("filterType"): entry for entry in symbol_info.get("filters", [])}
        warnings: list[str] = []
        adjusted_qty = order.qty
        lot_size = filters.get("LOT_SIZE")
        if lot_size:
            min_qty = float(lot_size.get("minQty", 0))
            step_size = float(lot_size.get("stepSize", 0))
            adjusted_qty = self._normalize_quantity(order.qty, step_size)
            if adjusted_qty <= 0:
                raise ValueError(f"Order quantity {order.qty} rounds down to zero for Binance step size {step_size}.")
            if adjusted_qty < min_qty:
                raise ValueError(f"Order quantity {order.qty} is below Binance minimum quantity {min_qty} for {symbol}.")
            if step_size > 0 and adjusted_qty != order.qty:
                warnings.append(f"Quantity adjusted from {order.qty} to {adjusted_qty} to match Binance step size {step_size}.")

        min_notional = filters.get("MIN_NOTIONAL")
        if min_notional:
            min_value = float(min_notional.get("minNotional", 0))
            notional = adjusted_qty * order.price
            if notional < min_value:
                raise ValueError(f"Order notional ${notional:.4f} is below Binance minimum notional {min_value} for {symbol}.")

        account = self.get_account_summary(settings, execution_mode)
        if not account.get("can_trade", False):
            raise ValueError("Binance account is not enabled for trading.")

        return {
            "ok": True,
            "warnings": warnings,
            "normalized_qty": adjusted_qty,
            "original_qty": order.qty,
            "estimated_notional": adjusted_qty * order.price,
        }

    def execute_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> BrokerExecutionResult:
        if execution_mode == "paper":
            return BrokerExecutionResult(
                broker_id=self.broker_id,
                execution_mode="paper",
                status="filled",
                message=f"Binance paper-filled {order.side} {order.qty} {order.symbol} @ {order.price}",
                filled_qty=order.qty,
                filled_price=order.price,
                metadata=order.metadata,
            )

        if not self.is_configured(settings):
            raise ValueError("Binance live trading requires binance_key and binance_secret in settings.")

        validation = self.validate_order(order, execution_mode, settings)
        normalized_qty = float(validation.get("normalized_qty", order.qty))

        payload = {
            "symbol": self._normalize_symbol(order.symbol),
            "side": order.side.upper(),
            "type": "MARKET",
            "quantity": normalized_qty,
            "newOrderRespType": "FULL",
        }
        response = self._signed_request("POST", "/api/v3/order", payload, settings)
        fills = response.get("fills", [])
        average_fill_price = order.price
        if fills:
            fill_value = sum(float(fill.get("price", 0)) * float(fill.get("qty", 0)) for fill in fills)
            fill_qty = sum(float(fill.get("qty", 0)) for fill in fills)
            if fill_qty > 0:
                average_fill_price = fill_value / fill_qty

        executed_qty = float(response.get("executedQty", order.qty))
        status = str(response.get("status", "UNKNOWN")).lower()

        return BrokerExecutionResult(
            broker_id=self.broker_id,
            execution_mode="live",
            status=status,
            message=f"Binance live order {status}: {order.side.upper()} {executed_qty} {order.symbol}",
            filled_qty=executed_qty,
            filled_price=average_fill_price,
            metadata={
                **response,
                "order_status": status,
                "broker_order_id": self._extract_broker_order_id(response),
                "requested_qty": order.qty,
                "normalized_qty": normalized_qty,
                "validation_warnings": validation.get("warnings", []),
            },
        )

    def test_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        validation = self.validate_order(order, execution_mode, settings)
        normalized_qty = float(validation.get("normalized_qty", order.qty))

        if execution_mode == "paper":
            return {
                "ok": True,
                "broker_id": self.broker_id,
                "execution_mode": execution_mode,
                "message": f"Binance paper test order accepted for {normalized_qty} {order.symbol}.",
                "validation": validation,
                "environment": "simulated",
            }

        payload = {
            "symbol": self._normalize_symbol(order.symbol),
            "side": order.side.upper(),
            "type": "MARKET",
            "quantity": normalized_qty,
        }
        self._signed_request("POST", "/api/v3/order/test", payload, settings)
        return {
            "ok": True,
            "broker_id": self.broker_id,
            "execution_mode": execution_mode,
            "message": f"Binance test order accepted for {normalized_qty} {order.symbol}.",
            "validation": validation,
            "environment": self._get_environment_label(settings),
        }

    def get_order_status(self, trade: dict, settings: dict) -> dict:
        if trade.get("execution_mode") != "live":
            return super().get_order_status(trade, settings)

        broker_order_id = trade.get("broker_order_id")
        if not broker_order_id:
            return super().get_order_status(trade, settings)

        response = self._signed_request(
            "GET",
            "/api/v3/order",
            {
                "symbol": self._normalize_symbol(trade.get("symbol", "")),
                "orderId": broker_order_id,
            },
            settings,
        )
        order_status = str(response.get("status", trade.get("order_status", "unknown"))).lower()
        orig_qty = float(response.get("origQty", trade.get("qty", 0)) or 0)
        executed_qty = float(response.get("executedQty", 0) or 0)
        return {
            "order_status": order_status,
            "broker_order_id": self._extract_broker_order_id(response) or broker_order_id,
            "metadata": {
                **response,
                "orig_qty": orig_qty,
                "executed_qty": executed_qty,
                "fill_progress_pct": (executed_qty / orig_qty * 100) if orig_qty > 0 else 0,
                "broker_reason": response.get("rejectReason") or response.get("status"),
            },
        }

    def cancel_order(self, trade: dict, settings: dict) -> dict:
        if trade.get("execution_mode") != "live":
            raise ValueError("Binance order cancellation is only available for live orders.")

        broker_order_id = trade.get("broker_order_id")
        if not broker_order_id:
            raise ValueError("This trade does not have a broker order id.")

        response = self._signed_request(
            "DELETE",
            "/api/v3/order",
            {
                "symbol": self._normalize_symbol(trade.get("symbol", "")),
                "orderId": broker_order_id,
            },
            settings,
        )
        order_status = str(response.get("status", "CANCELED")).lower()
        filled_qty = float(response.get("executedQty", trade.get("filled_qty", 0)) or 0)
        cumulative_quote = float(response.get("cummulativeQuoteQty", 0) or 0)
        filled_price = (cumulative_quote / filled_qty) if filled_qty > 0 and cumulative_quote > 0 else float(trade.get("filled_price", 0) or 0)
        return {
            "order_status": order_status,
            "broker_order_id": self._extract_broker_order_id(response) or broker_order_id,
            "filled_qty": filled_qty,
            "filled_price": filled_price,
            "metadata": {
                **response,
                "broker_reason": response.get("status"),
            },
            "message": f"Binance order {broker_order_id} canceled with status {order_status}.",
        }

    def list_open_orders(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        if execution_mode != "live":
            return []

        normalized_symbol = self._normalize_symbol(symbol) if symbol else ""
        params = {"symbol": normalized_symbol} if normalized_symbol else {}
        response = self._signed_request("GET", "/api/v3/openOrders", params, settings)
        if not isinstance(response, list):
            return []

        return [
            {
                "broker_order_id": self._extract_broker_order_id(order),
                "symbol": order.get("symbol", normalized_symbol),
                "side": str(order.get("side", "")).upper(),
                "status": str(order.get("status", "unknown")).lower(),
                "type": str(order.get("type", "MARKET")).lower(),
                "orig_qty": float(order.get("origQty", 0) or 0),
                "executed_qty": float(order.get("executedQty", 0) or 0),
                "price": float(order.get("price", 0) or 0),
                "time": int(order.get("time", 0) or 0),
            }
            for order in response
        ]

    def list_positions(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        account = self.get_account_summary(settings, execution_mode)
        if execution_mode == "paper":
            return []

        quote_assets = {"USDT", "USD", "BUSD", "USDC"}
        normalized_symbol = self._normalize_symbol(symbol) if symbol else ""
        balances = account.get("balances", [])
        positions: list[dict] = []
        for balance in balances:
            asset = str(balance.get("asset", ""))
            free = float(balance.get("free", 0) or 0)
            locked = float(balance.get("locked", 0) or 0)
            total_qty = free + locked
            if total_qty <= 0 or asset in quote_assets:
                continue
            if normalized_symbol and not normalized_symbol.startswith(asset):
                continue
            positions.append(
                {
                    "symbol": f"{asset}/{normalized_symbol[len(asset):]}" if normalized_symbol.startswith(asset) else asset,
                    "qty": total_qty,
                    "available_qty": free,
                    "locked_qty": locked,
                    "market_value": None,
                    "avg_entry_price": None,
                    "unrealized_pl": None,
                    "side": "long",
                }
            )
        return positions
