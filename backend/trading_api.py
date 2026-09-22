from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.broker_integration.base import BrokerOrder
from backend.broker_integration.registry import broker_registry
from core.trading_engine import trading_engine
from core.data_service import market_data
from core.risk_engine import risk_engine
from database.sqlite_manager import record_trade, get_settings, get_trades, get_trade_by_id, update_trade_order_state

router = APIRouter()

class TradingStatus(BaseModel):
    is_active: bool
    symbol: str = "BTC/USDT"
    asset_type: str = "crypto"
    interval: str = "1h"
    broker_id: str = "paper"
    execution_mode: str = "paper"
    strategy_code: str = ""


class TradingPreflightRequest(BaseModel):
    symbol: str
    asset_type: str = "crypto"
    broker_id: str = "paper"
    execution_mode: str = "paper"


class TradingTestOrderRequest(BaseModel):
    symbol: str
    asset_type: str = "crypto"
    broker_id: str = "paper"
    execution_mode: str = "paper"
    side: str = "BUY"
    qty: float = 1.0


class TradeCancelRequest(BaseModel):
    trade_id: int


class OpenOrdersQuery(BaseModel):
    symbol: str
    asset_type: str = "crypto"
    broker_id: str = "paper"
    execution_mode: str = "paper"

class LiveTradingManager:
    def __init__(self):
        self.is_running = False
        self.active_task = None
        self.config = {
            "symbol": "BTC/USDT",
            "asset_type": "crypto",
            "interval": "1h",
            "broker_id": "paper",
            "execution_mode": "paper",
            "strategy_code": ""
        }
        self.logs = []

    def log(self, message: str):
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        if len(self.logs) > 50:
            self.logs.pop(0)

    async def run_loop(self):
        self.log(
            f"Starting {self.config['execution_mode']} trading loop for {self.config['symbol']} via {self.config['broker_id']}..."
        )
        while self.is_running:
            try:
                # 1. Fetch latest data
                symbol = self.config["symbol"]
                asset_type = self.config.get("asset_type", "crypto")
                interval = self.config["interval"]
                broker_id = self.config.get("broker_id", "paper")
                execution_mode = self.config.get("execution_mode", "paper")
                strategy_code = self.config["strategy_code"]
                broker = broker_registry.get(broker_id)
                
                if not strategy_code:
                    self.log("No strategy code provided. Waiting...")
                    await asyncio.sleep(10)
                    continue

                if asset_type not in broker.supported_asset_types:
                    self.log(f"{broker.display_name} does not support asset type: {asset_type}")
                    await asyncio.sleep(60)
                    continue

                self.log(f"Fetching latest data for {symbol} ({asset_type})...")
                if asset_type == "stock":
                    df = market_data.get_stock_data(symbol, interval)
                else:
                    df = market_data.get_crypto_data(symbol, interval, limit=100)
                
                if df.empty:
                    self.log(f"Failed to fetch market data for {symbol}.")
                    await asyncio.sleep(60)
                    continue

                # Normalize columns to lowercase for strategy consistency
                df.columns = [c.lower() for c in df.columns]

                # 2. Evaluate strategy
                self.log("Evaluating strategy signals...")
                result_df = trading_engine.evaluate_strategy(strategy_code, df)
                signal = trading_engine.get_signal(result_df)
                
                if signal:
                    price_column = 'close' if 'close' in df.columns else 'Close'
                    last_price = float(df.iloc[-1][price_column])
                    self.log(f"SIGNAL DETECTED: {signal} at ${last_price}")

                    settings = get_settings() or {}
                    order = BrokerOrder(
                        symbol=symbol,
                        side=signal,
                        qty=1.0,
                        price=last_price,
                        asset_type=asset_type,
                        metadata={"interval": interval},
                    )
                    risk = risk_engine.evaluate_order(
                        side=order.side,
                        qty=order.qty,
                        price=order.price,
                        execution_mode=execution_mode,
                        settings=settings,
                    )
                    if not risk.approved:
                        self.log(f"RISK BLOCKED ORDER: {'; '.join(risk.reasons)}")
                        await asyncio.sleep(60)
                        continue

                    broker_validation = broker.validate_order(order, execution_mode, settings)
                    if not broker_validation.get("ok", False):
                        self.log(f"BROKER VALIDATION BLOCKED ORDER: {broker_validation}")
                        await asyncio.sleep(60)
                        continue

                    order.qty = float(broker_validation.get("normalized_qty", order.qty))
                    execution = broker.execute_order(order, execution_mode, settings)

                    record_trade(
                        symbol,
                        signal,
                        execution.filled_qty,
                        execution.filled_price,
                        is_paper=execution.execution_mode == "paper",
                        broker_id=execution.broker_id,
                        execution_mode=execution.execution_mode,
                        order_status=execution.status,
                        order_type="market",
                        broker_order_id=execution.metadata.get("broker_order_id"),
                        is_test=False,
                        metadata=execution.metadata,
                    )
                    self.log(execution.message)
                else:
                    self.log("No signal detected.")

            except Exception as e:
                self.log(f"ERROR in loop: {str(e)}")
            
            # Wait for next interval (e.g. 60 seconds)
            await asyncio.sleep(60)

    def start(self, symbol, asset_type, interval, strategy_code, broker_id, execution_mode):
        if self.is_running:
            return
        self.is_running = True
        self.config = {
            "symbol": symbol, 
            "asset_type": asset_type,
            "interval": interval, 
            "broker_id": broker_id,
            "execution_mode": execution_mode,
            "strategy_code": strategy_code
        }
        self.active_task = asyncio.create_task(self.run_loop())

    def stop(self):
        self.is_running = False
        if self.active_task:
            self.active_task.cancel()
            self.active_task = None
        self.log("Paper trading loop stopped.")

trading_manager = LiveTradingManager()


def resolve_market_price(symbol: str, asset_type: str) -> float:
    market_price = 1.0
    try:
        if asset_type == "stock":
            df = market_data.get_stock_data(symbol, "1d")
        else:
            df = market_data.get_crypto_data(symbol, "1h", limit=5)
        if not df.empty:
            price_column = "close" if "close" in df.columns else "Close"
            market_price = float(df.iloc[-1][price_column])
    except Exception:
        pass
    return market_price

@router.post("/api/trading/toggle")
async def toggle_trading(status: TradingStatus):
    if status.is_active:
        try:
            broker = broker_registry.get(status.broker_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if status.execution_mode == "live" and not broker.supports_live:
            raise HTTPException(status_code=400, detail=f"{broker.display_name} does not support live trading.")

        settings = get_settings() or {}
        if status.execution_mode == "live":
            if not bool(settings.get("risk_live_trading_enabled", False)):
                raise HTTPException(
                    status_code=400,
                    detail="Live trading is locked by the risk engine. Enable it explicitly only after validation.",
                )
            try:
                account = broker.get_account_summary(settings, status.execution_mode)
                if not account.get("can_trade", False):
                    raise HTTPException(status_code=400, detail=f"{broker.display_name} account is not trade-enabled.")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        trading_manager.start(
            status.symbol,
            status.asset_type,
            status.interval,
            status.strategy_code,
            status.broker_id,
            status.execution_mode,
        )
        return {"status": "started", "config": trading_manager.config}
    else:
        trading_manager.stop()
        return {"status": "stopped"}

@router.get("/api/trading/status")
def get_status():
    return {
        "is_active": trading_manager.is_running,
        "config": trading_manager.config,
        "logs": trading_manager.logs
    }

@router.get("/api/trading/history")
def get_history():
    return get_trades(limit=20)


@router.get("/api/trading/history/refresh")
def refresh_history_statuses():
    settings = get_settings() or {}
    trades = get_trades(limit=20)
    refreshed: list[dict] = []
    final_statuses = {"filled", "canceled", "cancelled", "rejected", "expired", "tested"}

    for trade in trades:
        if trade.get("is_test") or trade.get("execution_mode") != "live":
            refreshed.append(trade)
            continue

        if str(trade.get("order_status", "")).lower() in final_statuses:
            refreshed.append(trade)
            continue

        broker_id = trade.get("broker_id", "paper")
        try:
            broker = broker_registry.get(broker_id)
            status = broker.get_order_status(trade, settings)
            trade["order_status"] = status.get("order_status", trade.get("order_status"))
            trade["broker_order_id"] = status.get("broker_order_id", trade.get("broker_order_id"))
            trade["metadata"] = status.get("metadata", trade.get("metadata", {}))
            update_trade_order_state(
                trade["id"],
                trade["order_status"],
                trade.get("broker_order_id"),
                trade.get("metadata", {}),
            )
        except Exception as exc:
            trade.setdefault("metadata", {})
            trade["metadata"]["status_refresh_error"] = str(exc)
            trade["metadata"]["broker_reason"] = str(exc)
        refreshed.append(trade)

    return refreshed


@router.get("/api/trading/brokers")
def get_brokers():
    settings = get_settings() or {}
    return {"items": broker_registry.list_brokers(settings)}


@router.get("/api/trading/open-orders")
def get_open_orders(symbol: str, asset_type: str = "crypto", broker_id: str = "paper", execution_mode: str = "paper"):
    settings = get_settings() or {}
    try:
        broker = broker_registry.get(broker_id)
        items = broker.list_open_orders(symbol, asset_type, settings, execution_mode)
        return {
            "items": items,
            "broker_id": broker_id,
            "execution_mode": execution_mode,
            "symbol": symbol,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/trading/positions")
def get_positions(symbol: str, asset_type: str = "crypto", broker_id: str = "paper", execution_mode: str = "paper"):
    settings = get_settings() or {}
    try:
        broker = broker_registry.get(broker_id)
        items = broker.list_positions(symbol, asset_type, settings, execution_mode)
        return {
            "items": items,
            "broker_id": broker_id,
            "execution_mode": execution_mode,
            "symbol": symbol,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/trading/account/{broker_id}")
def get_broker_account(broker_id: str, execution_mode: str = "paper"):
    settings = get_settings() or {}
    try:
        broker = broker_registry.get(broker_id)
        return broker.get_account_summary(settings, execution_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/trading/preflight")
def run_trading_preflight(request: TradingPreflightRequest):
    settings = get_settings() or {}
    try:
        broker = broker_registry.get(request.broker_id)
        market_price = resolve_market_price(request.symbol, request.asset_type)
        account = broker.get_account_summary(settings, request.execution_mode)
        order = BrokerOrder(
            symbol=request.symbol,
            side="BUY",
            qty=1.0,
            price=market_price,
            asset_type=request.asset_type,
            metadata={},
        )
        risk = risk_engine.evaluate_order(
            side=order.side,
            qty=order.qty,
            price=order.price,
            execution_mode=request.execution_mode,
            settings=settings,
        )
        validation = broker.validate_order(order, request.execution_mode, settings)
        return {
            "broker": broker.get_status(settings),
            "account": account,
            "risk": risk.as_dict(),
            "validation": validation,
            "market_price": market_price,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/trading/test-order")
def run_trading_test_order(request: TradingTestOrderRequest):
    settings = get_settings() or {}
    try:
        broker = broker_registry.get(request.broker_id)
        market_price = resolve_market_price(request.symbol, request.asset_type)
        result = broker.test_order(
            BrokerOrder(
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                price=market_price,
                asset_type=request.asset_type,
                metadata={"source": "manual_test"},
            ),
            request.execution_mode,
            settings,
        )
        validation = result.get("validation", {})
        normalized_qty = float(validation.get("normalized_qty", request.qty))
        record_trade(
            request.symbol,
            request.side,
            normalized_qty,
            market_price,
            is_paper=request.execution_mode == "paper",
            broker_id=result.get("broker_id", request.broker_id),
            execution_mode=result.get("execution_mode", request.execution_mode),
            order_status="tested",
            order_type="market_test",
            broker_order_id=None,
            is_test=True,
            metadata=result,
        )
        trading_manager.log(f"TEST ORDER: {result.get('message', 'Broker test order completed.')}")
        return {
            **result,
            "market_price": market_price,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/trading/cancel-order")
def cancel_trade_order(request: TradeCancelRequest):
    settings = get_settings() or {}
    trade = get_trade_by_id(request.trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found.")

    final_statuses = {"filled", "canceled", "cancelled", "rejected", "expired", "tested"}
    if str(trade.get("order_status", "")).lower() in final_statuses:
        raise HTTPException(status_code=400, detail="This order is already in a final state.")

    try:
        broker = broker_registry.get(trade.get("broker_id", "paper"))
        result = broker.cancel_order(trade, settings)
        update_trade_order_state(
            trade["id"],
            result.get("order_status", "canceled"),
            result.get("broker_order_id"),
            result.get("metadata", {}),
        )
        trading_manager.log(result.get("message", f"Canceled order for trade {trade['id']}."))
        return {
            "status": "success",
            "trade_id": trade["id"],
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
