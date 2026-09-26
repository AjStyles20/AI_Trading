from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import BrokerClient, BrokerExecutionResult, BrokerOrder
from core.credential_provider import resolve_api_keys


class BitgetBroker(BrokerClient):
    broker_id = "bitget"
    display_name = "Bitget"
    supports_live = True
    supported_asset_types = ("crypto",)

    def _get_api_keys(self, settings: dict) -> dict:
        return resolve_api_keys(settings)

    def _use_demo(self, settings: dict) -> bool:
        api_keys = self._get_api_keys(settings)
        return str(api_keys.get("bitget_demo", "")).strip().lower() in {"1", "true", "yes", "on"}

    def _get_environment_label(self, settings: dict) -> str:
        return "demo" if self._use_demo(settings) else "live"

    def _get_base_url(self) -> str:
        return "https://api.bitget.com"

    def _get_credentials(self, settings: dict, demo: bool) -> tuple[str, str, str]:
        api_keys = self._get_api_keys(settings)
        if demo:
            api_key = api_keys.get("bitget_demo_key", "")
            api_secret = api_keys.get("bitget_demo_secret", "")
            passphrase = api_keys.get("bitget_demo_passphrase", "")
            if not api_key or not api_secret or not passphrase:
                raise ValueError(
                    "Bitget demo trading requires bitget_demo_key, bitget_demo_secret, and bitget_demo_passphrase."
                )
            return api_key, api_secret, passphrase

        api_key = api_keys.get("bitget_key", "")
        api_secret = api_keys.get("bitget_secret", "")
        passphrase = api_keys.get("bitget_passphrase", "")
        if not api_key or not api_secret or not passphrase:
            raise ValueError("Bitget live trading requires bitget_key, bitget_secret, and bitget_passphrase.")
        return api_key, api_secret, passphrase

    def _sign(self, secret: str, payload: str) -> str:
        signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _request(
        self,
        method: str,
        path: str,
        settings: dict,
        params: dict[str, str | int | float] | None = None,
        body: dict | None = None,
    ) -> dict | list:
        demo = self._use_demo(settings)
        api_key, api_secret, passphrase = self._get_credentials(settings, demo)
        timestamp = str(int(time.time() * 1000))
        query_string = urllib.parse.urlencode(params) if params else ""
        body_payload = json.dumps(body, separators=(",", ":")) if body else ""
        request_path = f"{path}?{query_string}" if query_string else path
        prehash = f"{timestamp}{method.upper()}{request_path}{body_payload}"
        signature = self._sign(api_secret, prehash)

        headers = {
            "ACCESS-KEY": api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-PASSPHRASE": passphrase,
            "ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

        url = f"{self._get_base_url()}{request_path}"
        data = body_payload.encode("utf-8") if body_payload else None
        request = urllib.request.Request(url, method=method.upper(), headers=headers, data=data)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Bitget API error ({exc.code}): {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Bitget network error: {exc.reason}") from exc

        code = str(payload.get("code", ""))
        if code and code != "00000":
            raise ValueError(f"Bitget API error ({code}): {payload.get('msg') or payload.get('message')}")
        return payload.get("data", payload)

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    def get_status(self, settings: dict) -> dict:
        status = super().get_status(settings)
        status["environment"] = self._get_environment_label(settings)
        return status

    def is_configured(self, settings: dict) -> bool:
        api_keys = self._get_api_keys(settings)
        if self._use_demo(settings):
            return bool(
                api_keys.get("bitget_demo_key")
                and api_keys.get("bitget_demo_secret")
                and api_keys.get("bitget_demo_passphrase")
            )
        return bool(
            api_keys.get("bitget_key")
            and api_keys.get("bitget_secret")
            and api_keys.get("bitget_passphrase")
        )

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
                "warnings": ["Bitget paper mode uses simulated balances."],
            }

        assets = self._request("GET", "/api/v2/spot/account/assets", settings, params={"assetType": "hold_only"})
        balances: list[dict] = []
        for item in assets or []:
            asset = str(item.get("coin") or item.get("asset") or "")
            free = float(item.get("available", 0) or item.get("free", 0) or 0)
            locked = float(item.get("frozen", 0) or item.get("locked", 0) or 0)
            if free <= 0 and locked <= 0:
                continue
            balances.append({"asset": asset, "free": free, "locked": locked})

        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "execution_mode": execution_mode,
            "environment": self._get_environment_label(settings),
            "configured": self.is_configured(settings),
            "can_trade": self.is_configured(settings),
            "balances": balances[:10],
            "warnings": ["Bitget demo mode is enabled."] if self._use_demo(settings) else [],
        }

    def validate_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        if execution_mode == "paper":
            return super().validate_order(order, execution_mode, settings)

        if order.qty <= 0:
            raise ValueError("Order quantity must be greater than 0.")
        if order.price <= 0:
            raise ValueError("Order price must be greater than 0.")

        self._get_credentials(settings, self._use_demo(settings))
        return {
            "ok": True,
            "warnings": [],
            "normalized_qty": order.qty,
            "original_qty": order.qty,
            "estimated_notional": order.qty * order.price,
        }

    def execute_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> BrokerExecutionResult:
        if execution_mode == "paper":
            return BrokerExecutionResult(
                broker_id=self.broker_id,
                execution_mode="paper",
                status="filled",
                message=f"Bitget paper-filled {order.side} {order.qty} {order.symbol} @ {order.price}",
                filled_qty=order.qty,
                filled_price=order.price,
                metadata=order.metadata,
            )

        validation = self.validate_order(order, execution_mode, settings)
        payload = {
            "symbol": self._normalize_symbol(order.symbol),
            "side": order.side.lower(),
            "orderType": "market",
            "size": str(validation.get("normalized_qty", order.qty)),
            "clientOid": str(int(time.time() * 1000)),
        }
        response = self._request("POST", "/api/v2/spot/trade/place-order", settings, body=payload)
        broker_order_id = None
        if isinstance(response, dict):
            broker_order_id = response.get("orderId") or response.get("order_id")

        return BrokerExecutionResult(
            broker_id=self.broker_id,
            execution_mode=execution_mode,
            status="submitted",
            message=f"Bitget order submitted: {order.side.upper()} {order.qty} {order.symbol}",
            filled_qty=0,
            filled_price=order.price,
            metadata={
                **order.metadata,
                "broker_order_id": broker_order_id,
                "order_status": "submitted",
                "requested_qty": order.qty,
                "normalized_qty": validation.get("normalized_qty", order.qty),
            },
        )

    def test_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        validation = self.validate_order(order, execution_mode, settings)
        env = "paper" if execution_mode == "paper" else self._get_environment_label(settings)
        return {
            "ok": True,
            "broker_id": self.broker_id,
            "execution_mode": execution_mode,
            "message": f"Bitget {env} test order validated successfully.",
            "validation": validation,
            "environment": env,
        }

    def get_order_status(self, trade: dict, settings: dict) -> dict:
        broker_order_id = trade.get("broker_order_id")
        if not broker_order_id:
            return super().get_order_status(trade, settings)

        response = self._request(
            "GET",
            "/api/v2/spot/trade/orderInfo",
            settings,
            params={"orderId": broker_order_id},
        )
        if not isinstance(response, dict):
            return super().get_order_status(trade, settings)
        order_status = str(response.get("status", "unknown")).lower()
        executed_qty = float(response.get("baseVolume", 0) or response.get("filledQty", 0) or 0)
        orig_qty = float(response.get("size", trade.get("qty", 0)) or 0)
        return {
            "order_status": order_status,
            "broker_order_id": broker_order_id,
            "metadata": {
                **response,
                "orig_qty": orig_qty,
                "executed_qty": executed_qty,
                "fill_progress_pct": (executed_qty / orig_qty * 100) if orig_qty > 0 else 0,
                "broker_reason": response.get("status"),
            },
        }

    def cancel_order(self, trade: dict, settings: dict) -> dict:
        raise ValueError("Bitget order cancellation is not wired yet in this build.")

    def list_open_orders(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        if execution_mode == "paper":
            return []

        end_time = int(time.time() * 1000)
        start_time = end_time - 24 * 60 * 60 * 1000
        params: dict[str, str | int] = {"startTime": start_time, "endTime": end_time}
        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)

        response = self._request("GET", "/api/v2/spot/trade/unfilled-orders", settings, params=params)
        if not isinstance(response, dict):
            return []

        orders = response.get("orderList") or response.get("list") or response.get("data") or []
        if not isinstance(orders, list):
            return []

        return [
            {
                "broker_order_id": order.get("orderId") or order.get("order_id"),
                "symbol": order.get("symbol", symbol),
                "side": str(order.get("side", "")).upper(),
                "status": str(order.get("status", "unknown")).lower(),
                "type": str(order.get("orderType", order.get("type", "market"))).lower(),
                "orig_qty": float(order.get("size", 0) or 0),
                "executed_qty": float(order.get("baseVolume", 0) or order.get("filledQty", 0) or 0),
                "price": float(order.get("price", 0) or 0),
                "time": int(order.get("cTime", 0) or order.get("time", 0) or 0),
            }
            for order in orders
        ]

    def list_positions(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        if execution_mode == "paper":
            return []

        assets = self._request("GET", "/api/v2/spot/account/assets", settings, params={"assetType": "hold_only"})
        positions: list[dict] = []
        for item in assets or []:
            asset = str(item.get("coin") or item.get("asset") or "")
            free = float(item.get("available", 0) or item.get("free", 0) or 0)
            locked = float(item.get("frozen", 0) or item.get("locked", 0) or 0)
            total = free + locked
            if total <= 0:
                continue
            if symbol:
                normalized_symbol = self._normalize_symbol(symbol)
                if normalized_symbol and not normalized_symbol.startswith(asset):
                    continue
            positions.append(
                {
                    "symbol": asset,
                    "qty": total,
                    "available_qty": free,
                    "locked_qty": locked,
                    "market_value": None,
                    "avg_entry_price": None,
                    "unrealized_pl": None,
                    "side": "long",
                }
            )
        return positions
