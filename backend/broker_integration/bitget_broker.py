from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from .base import BrokerClient, BrokerExecutionResult, BrokerOrder, BrokerQuote
from core.credential_provider import resolve_api_keys


# Buys are sent as marketable limit orders, immediate-or-cancel, sized in the
# base coin. A plain market buy is sized in the quote coin on Bitget, so its fill
# could exceed the approved base quantity when the price moves; a limit buy can
# never fill more than its quantity, and the cap bounds slippage. The cap must
# stay below Bitget's buyLimitPriceRatio (2% for BTCUSDT).
BUY_PRICE_CAP = Decimal("0.005")
SYMBOL_RULES_TTL_SECONDS = 3600


class BitgetBroker(BrokerClient):
    broker_id = "bitget"
    display_name = "Bitget"
    supports_live = True
    supported_asset_types = ("crypto",)

    def _get_api_keys(self, settings: dict) -> dict:
        return resolve_api_keys(settings)

    def _use_demo(self, settings: dict) -> bool:
        return settings.get("bitget_environment", "live") == "demo"

    def _get_environment_label(self, settings: dict) -> str:
        return "demo" if self._use_demo(settings) else "live"

    # Bitget has two account types with separate APIs: classic accounts use the
    # v2 spot endpoints, Unified Trading Accounts (UTA) the v3 endpoints. A
    # unified account answers v2 balance calls with nothing, so the type must be
    # chosen to match the account. https://www.bitget.com/docs/classic/uta-api-upgrade-guide
    def _use_unified(self, settings: dict) -> bool:
        return settings.get("bitget_account_type", "classic") == "unified"

    def _get_account_label(self, settings: dict) -> str:
        return "unified" if self._use_unified(settings) else "classic"

    def _holdings(self, settings: dict) -> list[tuple[str, float, float]]:
        """Non-zero spot holdings as (coin, available, locked), for either account type."""
        holdings: list[tuple[str, float, float]] = []
        if self._use_unified(settings):
            items = self._unified_account(settings).get("assets") or []
            for item in items:
                coin = str(item.get("coin") or "")
                available = float(item.get("available", 0) or 0)
                balance = float(item.get("balance", 0) or 0)
                locked = float(item.get("locked", 0) or 0) or max(balance - available, 0.0)
                holdings.append((coin, available, locked))
        else:
            assets = self._request("GET", "/api/v2/spot/account/assets", settings, params={"assetType": "hold_only"})
            for item in assets or []:
                coin = str(item.get("coin") or item.get("asset") or "")
                available = float(item.get("available", 0) or item.get("free", 0) or 0)
                locked = float(item.get("frozen", 0) or item.get("locked", 0) or 0)
                holdings.append((coin, available, locked))
        return [(coin, free, locked) for coin, free, locked in holdings if coin and free + locked > 0]

    def _unified_account(self, settings: dict) -> dict:
        account = self._request("GET", "/api/v3/account/assets", settings)
        return account if isinstance(account, dict) else {}

    def _unified_summary_balances(self, settings: dict) -> tuple[list[dict], float | None]:
        """Unified-account balances with each coin's USD value, plus total equity."""
        account = self._unified_account(settings)
        balances = []
        for item in account.get("assets") or []:
            coin = str(item.get("coin") or "")
            available = float(item.get("available", 0) or 0)
            balance = float(item.get("balance", 0) or 0)
            locked = float(item.get("locked", 0) or 0) or max(balance - available, 0.0)
            if not coin or available + locked <= 0:
                continue
            usd_value = item.get("usdValue")
            balances.append({
                "asset": coin,
                "free": available,
                "locked": locked,
                "usd_value": float(usd_value) if usd_value not in (None, "") else None,
            })
        balances.sort(key=lambda entry: entry["usd_value"] or 0.0, reverse=True)
        equity = account.get("accountEquity")
        return balances, (float(equity) if equity not in (None, "") else None)

    def _unified_live_blocked(self, settings: dict) -> bool:
        return self._use_unified(settings) and not self._use_demo(settings)

    def _reject_unified_trading(self, settings: dict) -> None:
        # Unified-account orders use the v3 API. They run in demo trading only
        # until that path has been verified there; real-money unified orders are
        # refused here, at broker validation, so the guarded submission path
        # never records an order intent or contacts Bitget.
        if self._unified_live_blocked(settings):
            raise ValueError(
                "Bitget unified-account trading is enabled in demo only until it has been verified there. "
                "Switch on Bitget demo trading to place unified-account orders."
            )

    def _symbol_rules(self, symbol: str, settings: dict) -> dict:
        """Precision, minimum value and status for a spot symbol (public data, cached)."""
        unified = self._use_unified(settings)
        key = ("unified" if unified else "classic", symbol)
        cache = self.__dict__.setdefault("_rules_cache", {})
        cached = cache.get(key)
        if cached and time.monotonic() - cached[0] < SYMBOL_RULES_TTL_SECONDS:
            return cached[1]
        if unified:
            payload = self._public_request("/api/v3/market/instruments", params={"category": "SPOT", "symbol": symbol})
        else:
            payload = self._public_request("/api/v2/spot/public/symbols", params={"symbol": symbol})
        item = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
            raise ValueError(f"Bitget has no spot symbol rules for {symbol}.")
        rules = {
            "status": str(item.get("status", "")).lower(),
            "quantity_decimals": int(item.get("quantityPrecision")),
            "price_decimals": int(item.get("pricePrecision")),
            "min_order_value": Decimal(str(item.get("minOrderAmount" if unified else "minTradeUSDT") or "0")),
            "buy_limit_ratio": Decimal(str(item.get("buyLimitPriceRatio") or "0")),
        }
        cache[key] = (time.monotonic(), rules)
        return rules

    @staticmethod
    def _quantize(value: Decimal, decimals: int, rounding: str) -> Decimal:
        return value.quantize(Decimal(1).scaleb(-decimals), rounding=rounding)

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        return format(value, "f")

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
        if demo:
            # Bitget routes a request to demo trading only when this header is
            # present; a demo key without it is sent to the live environment
            # and rejected. https://www.bitget.com/docs/classic/demo-trading/rest-api
            headers["paptrading"] = "1"

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

    def _public_request(
        self,
        path: str,
        params: dict[str, str | int | float] | None = None,
    ) -> dict | list:
        query_string = urllib.parse.urlencode(params) if params else ""
        request_path = f"{path}?{query_string}" if query_string else path
        request = urllib.request.Request(
            f"{self._get_base_url()}{request_path}",
            method="GET",
            headers={"locale": "en-US"},
        )
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
        status["account_type"] = self._get_account_label(settings)
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

    def get_quote(
        self,
        symbol: str,
        asset_type: str,
        settings: dict,
        execution_mode: str,
        reference_price: float | None = None,
    ) -> BrokerQuote:
        if asset_type != "crypto":
            raise ValueError("Bitget quote adapter supports crypto only.")
        normalized = self._normalize_symbol(symbol)
        payload = self._public_request(
            "/api/v2/spot/market/tickers",
            params={"symbol": normalized},
        )
        item = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(item, dict):
            raise ValueError(f"Bitget returned an invalid quote payload for {normalized}.")
        bid = float(item.get("bidPr", 0) or item.get("bidPrice", 0) or 0)
        ask = float(item.get("askPr", 0) or item.get("askPrice", 0) or 0)
        last = float(item.get("lastPr", 0) or item.get("last", 0) or 0)
        if bid <= 0 and ask <= 0 and last <= 0:
            raise ValueError(f"Bitget returned an invalid quote for {normalized}.")
        return BrokerQuote(
            broker_id=self.broker_id, symbol=symbol,
            bid=bid if bid > 0 else None, ask=ask if ask > 0 else None,
            last=last if last > 0 else None,
            timestamp=str(item.get("ts")) if item.get("ts") is not None else None,
            source=f"bitget:{self._get_environment_label(settings)}:ticker",
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

        total_equity_usd = None
        if self._use_unified(settings):
            balances, total_equity_usd = self._unified_summary_balances(settings)
        else:
            balances = [
                {"asset": coin, "free": free, "locked": locked}
                for coin, free, locked in self._holdings(settings)
            ]

        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "execution_mode": execution_mode,
            "environment": self._get_environment_label(settings),
            "account_type": self._get_account_label(settings),
            "configured": self.is_configured(settings),
            "can_trade": self.is_configured(settings) and not self._unified_live_blocked(settings),
            "balances": balances,
            "total_equity_usd": total_equity_usd,
            "warnings": ["Bitget demo mode is enabled."] if self._use_demo(settings) else [],
        }

    def validate_order(self, order: BrokerOrder, execution_mode: str, settings: dict) -> dict:
        if execution_mode == "paper":
            return super().validate_order(order, execution_mode, settings)

        self._reject_unified_trading(settings)
        if order.qty <= 0:
            raise ValueError("Order quantity must be greater than 0.")
        if order.price <= 0:
            raise ValueError("Order price must be greater than 0.")
        side = order.side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported order side: {order.side}.")

        self._get_credentials(settings, self._use_demo(settings))
        symbol = self._normalize_symbol(order.symbol)
        rules = self._symbol_rules(symbol, settings)
        if rules["status"] != "online":
            raise ValueError(f"Bitget is not trading {symbol} (status: {rules['status'] or 'unknown'}).")

        # Round down so the order never exceeds the quantity risk approved.
        qty = self._quantize(Decimal(str(order.qty)), rules["quantity_decimals"], ROUND_DOWN)
        if qty <= 0:
            raise ValueError(f"Order quantity rounds to zero at Bitget's {rules['quantity_decimals']} decimal places.")
        reference = Decimal(str(order.price))
        notional = qty * reference
        if notional < rules["min_order_value"]:
            raise ValueError(
                f"Order value {self._decimal_text(notional)} is below Bitget's minimum of "
                f"{self._decimal_text(rules['min_order_value'])} USDT for {symbol}."
            )

        validation = {
            "ok": True,
            "warnings": [],
            "normalized_qty": float(qty),
            "original_qty": order.qty,
            "estimated_notional": float(notional),
            "order_type": "market",
        }
        if side == "BUY":
            limit_price = self._quantize(reference * (1 + BUY_PRICE_CAP), rules["price_decimals"], ROUND_UP)
            if rules["buy_limit_ratio"] > 0 and limit_price > reference * (1 + rules["buy_limit_ratio"]):
                raise ValueError(f"Buy price cap exceeds Bitget's allowed range for {symbol}.")
            validation.update(
                order_type="limit_ioc",
                limit_price=float(limit_price),
                max_notional=float(qty * limit_price),
            )
        return validation

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

        self._reject_unified_trading(settings)
        validation = self.validate_order(order, execution_mode, settings)
        symbol = self._normalize_symbol(order.symbol)
        rules = self._symbol_rules(symbol, settings)
        qty_text = self._decimal_text(
            self._quantize(Decimal(str(validation["normalized_qty"])), rules["quantity_decimals"], ROUND_DOWN)
        )
        client_oid = order.metadata.get("client_order_id") or str(int(time.time() * 1000))
        is_buy = order.side.upper() == "BUY"
        price_text = (
            self._decimal_text(self._quantize(Decimal(str(validation["limit_price"])), rules["price_decimals"], ROUND_UP))
            if is_buy else None
        )
        if self._use_unified(settings):
            payload = {"category": "SPOT", "symbol": symbol, "side": "buy" if is_buy else "sell", "qty": qty_text, "clientOid": client_oid}
            if is_buy:
                payload.update(orderType="limit", price=price_text, timeInForce="ioc")
            else:
                payload["orderType"] = "market"
            path = "/api/v3/trade/place-order"
        else:
            # Classic spot: `size` is the base quantity for limit orders and
            # market sells. The IOC flag is `force` on the v2 spot API.
            payload = {"symbol": symbol, "side": "buy" if is_buy else "sell", "size": qty_text, "clientOid": client_oid}
            if is_buy:
                payload.update(orderType="limit", price=price_text, force="ioc")
            else:
                payload["orderType"] = "market"
            path = "/api/v2/spot/trade/place-order"
        response = self._request("POST", path, settings, body=payload)
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
                "order_type": validation.get("order_type"),
                "limit_price": validation.get("limit_price"),
                "account_type": self._get_account_label(settings),
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
        client_order_id = (trade.get("metadata") or {}).get("client_order_id")
        if not broker_order_id and not client_order_id:
            return super().get_order_status(trade, settings)
        self._reject_unified_trading(settings)
        if self._use_unified(settings):
            return self._unified_order_status(trade, settings, broker_order_id, client_order_id)

        response = self._request(
            "GET",
            "/api/v2/spot/trade/orderInfo",
            settings,
            params={"orderId": broker_order_id} if broker_order_id else {"clientOid": client_order_id},
        )
        if not isinstance(response, dict):
            return super().get_order_status(trade, settings)
        order_status = str(response.get("status", "unknown")).lower()
        executed_qty = float(response.get("baseVolume", 0) or response.get("filledQty", 0) or 0)
        orig_qty = float(response.get("size", trade.get("qty", 0)) or 0)
        filled_price = float(response.get("priceAvg", 0) or response.get("price", 0) or 0) if executed_qty > 0 else 0.0
        return {
            "order_status": order_status,
            "broker_order_id": response.get("orderId") or broker_order_id,
            "filled_qty": executed_qty,
            "filled_price": filled_price,
            "metadata": {
                **response,
                "orig_qty": orig_qty,
                "executed_qty": executed_qty,
                "fill_progress_pct": (executed_qty / orig_qty * 100) if orig_qty > 0 else 0,
                "broker_reason": response.get("status"),
            },
        }

    def _unified_order_status(self, trade: dict, settings: dict, broker_order_id, client_order_id) -> dict:
        response = self._request(
            "GET",
            "/api/v3/trade/order-info",
            settings,
            params={"orderId": broker_order_id} if broker_order_id else {"clientOid": client_order_id},
        )
        if not isinstance(response, dict) or not response.get("orderStatus"):
            raise ValueError("Bitget returned no order status; the order stays unresolved.")
        order_status = str(response["orderStatus"]).lower()
        executed_qty = float(response.get("cumExecQty", 0) or 0)
        orig_qty = float(response.get("qty", trade.get("qty", 0)) or 0)
        filled_price = float(response.get("avgPrice", 0) or 0) if executed_qty > 0 else 0.0
        return {
            "order_status": order_status,
            "broker_order_id": response.get("orderId") or broker_order_id,
            "filled_qty": executed_qty,
            "filled_price": filled_price,
            "metadata": {
                **response,
                "orig_qty": orig_qty,
                "executed_qty": executed_qty,
                "fill_progress_pct": (executed_qty / orig_qty * 100) if orig_qty > 0 else 0,
                "broker_reason": response.get("orderStatus"),
            },
        }

    def cancel_order(self, trade: dict, settings: dict) -> dict:
        if not self._use_unified(settings):
            raise ValueError("Bitget order cancellation is not wired yet for classic accounts.")
        self._reject_unified_trading(settings)
        broker_order_id = trade.get("broker_order_id")
        client_order_id = (trade.get("metadata") or {}).get("client_order_id")
        if not broker_order_id and not client_order_id:
            raise ValueError("This trade has no Bitget order id or client order id.")
        body = {"category": "SPOT", **({"orderId": broker_order_id} if broker_order_id else {"clientOid": client_order_id})}
        self._request("POST", "/api/v3/trade/cancel-order", settings, body=body)
        # Acceptance of a cancel is not a final state; reconciliation confirms it.
        return {
            "order_status": "cancel_requested",
            "broker_order_id": broker_order_id,
            "metadata": {
                "broker_reason": "cancel_requested",
                "executed_qty": float(trade.get("filled_qty", 0) or 0),
            },
        }

    def list_open_orders(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        if execution_mode == "paper":
            return []
        if self._use_unified(settings):
            return self._list_unified_open_orders(symbol, settings)

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

    def _list_unified_open_orders(self, symbol: str, settings: dict) -> list[dict]:
        params: dict[str, str] = {"category": "SPOT"}
        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)
        response = self._request("GET", "/api/v3/trade/unfilled-orders", settings, params=params)
        orders = response.get("list", []) if isinstance(response, dict) else []
        return [
            {
                "broker_order_id": order.get("orderId"),
                "symbol": order.get("symbol", symbol),
                "side": str(order.get("side", "")).upper(),
                "status": str(order.get("orderStatus", "unknown")).lower(),
                "type": str(order.get("orderType", "market")).lower(),
                "orig_qty": float(order.get("qty", 0) or 0),
                "executed_qty": float(order.get("cumExecQty", 0) or 0),
                "price": float(order.get("price", 0) or 0),
                "time": int(order.get("createdTime", 0) or 0),
            }
            for order in orders or []
            if isinstance(order, dict)
        ]

    def list_positions(self, symbol: str, asset_type: str, settings: dict, execution_mode: str) -> list[dict]:
        if execution_mode == "paper":
            return []

        positions: list[dict] = []
        for asset, free, locked in self._holdings(settings):
            total = free + locked
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
