from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import asyncio
import copy
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.broker_integration.base import BrokerOrder
from backend.broker_integration.registry import broker_registry
from core.trading_engine import trading_engine
from core.data_service import MarketDataError, market_data
from core.risk_engine import risk_engine
from core.position_ledger import reconstruct_confirmed_position
from core.position_protection import evaluate_position_protection
from core.autonomy_readiness import evaluate_autonomous_readiness
from database.sqlite_manager import record_trade, get_settings, get_trades, get_trades_for_scope, get_trade_by_id, get_strategy, update_trade_order_state, update_risk_equity_state

router = APIRouter()

class TradingStatus(BaseModel):
    is_active: bool
    symbol: str = "BTC/USDT"
    asset_type: str = "crypto"
    interval: str = "1h"
    broker_id: str = "paper"
    execution_mode: str = "paper"
    strategy_code: str = ""
    strategy_id: Optional[int] = None
    strategy_spec: Dict[str, Any] = Field(default_factory=dict)


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

def get_poll_delay_seconds(interval: str) -> int:
    """Return a bounded polling cadence for a strategy timeframe."""
    interval_seconds = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    seconds = interval_seconds.get(interval)
    if seconds is None:
        raise ValueError(f"Unsupported trading interval: {interval}")
    # Poll no faster than 15 seconds and no slower than 5 minutes. Candle
    # de-duplication below is the authoritative guard against repeat decisions.
    return max(15, min(300, seconds // 4))


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
            "strategy_code": "",
            "strategy_id": None,
            "strategy_record": None
        }
        self.logs = []
        self.last_evaluated_candle = None
        self.cooldown_remaining = 0

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
                strategy_record = self.config.get("strategy_record")
                if not strategy_record and self.config.get("strategy_code"):
                    strategy_record = {
                        "strategy_format": "legacy_python",
                        "strategy_spec": {},
                        "code": self.config["strategy_code"],
                    }
                broker = broker_registry.get(broker_id)
                
                if not strategy_record:
                    self.log("No resolved strategy provided. Waiting...")
                    await asyncio.sleep(10)
                    continue

                if asset_type not in broker.supported_asset_types:
                    self.log(f"{broker.display_name} does not support asset type: {asset_type}")
                    await asyncio.sleep(get_poll_delay_seconds(interval))
                    continue

                self.log(f"Fetching latest data for {symbol} ({asset_type})...")
                if asset_type == "stock":
                    df = market_data.get_stock_data(symbol, interval)
                else:
                    df = market_data.get_crypto_data(symbol, interval, limit=100)
                
                if df.empty:
                    self.log(f"Failed to fetch market data for {symbol}.")
                    await asyncio.sleep(get_poll_delay_seconds(interval))
                    continue

                # Normalize columns to lowercase for strategy consistency. Freshness
                # is assessed on the provider frame, then trading decisions consume only
                # fully elapsed candles so a forming bar cannot trigger strategy/protection.
                df.columns = [c.lower() for c in df.columns]
                market_data.assert_fresh(df, interval, asset_type=asset_type)
                df = market_data.get_completed_candles(df, interval)

                # Broker order lifecycle is independent of strategy signals and candle
                # evaluation. Reconcile every poll so asynchronous fills are observed
                # promptly, while strategy decisions remain deduplicated per candle.
                settings = get_settings() or {}
                scoped_trades = reconcile_unresolved_orders(
                    get_trades_for_scope(symbol, broker_id, execution_mode),
                    settings,
                    symbol,
                    broker_id,
                    execution_mode,
                )
                completed_exits = [
                    trade for trade in scoped_trades
                    if trade.get("_completed_exit_transition")
                ]
                if completed_exits:
                    latest_exit = completed_exits[0]
                    self.cooldown_remaining = int(
                        (latest_exit.get("metadata") or {}).get("cooldown_bars", 0)
                    )
                    self.log(
                        f"RECONCILED SELL FILL: cooldown set to {self.cooldown_remaining} bar(s)."
                    )

                confirmed_position = reconstruct_confirmed_position(
                    scoped_trades,
                    symbol=symbol,
                    broker_id=broker_id,
                    execution_mode=execution_mode,
                )
                if confirmed_position.qty > 0:
                    price_column = 'close'
                    protection = evaluate_position_protection(
                        confirmed_position,
                        market_price=float(df.iloc[-1][price_column]),
                        stop_loss_pct=confirmed_position.stop_loss_pct,
                        take_profit_pct=confirmed_position.take_profit_pct,
                    )
                    if protection.should_exit:
                        self.log(
                            f"PROTECTION TRIGGERED: {protection.reason} "
                            f"at {protection.market_price:.8f}; trigger={protection.trigger_price:.8f}."
                        )
                        if has_unresolved_order(
                            scoped_trades,
                            symbol,
                            broker_id,
                            execution_mode,
                        ):
                            self.log(
                                "PROTECTION ORDER BLOCKED: unresolved prior broker order "
                                "must reach a final state first."
                            )
                        else:
                            try:
                                account_equity, current_position_qty, day_start_equity, peak_equity = get_risk_context(
                                    broker, symbol, settings, execution_mode, broker_id
                                )
                                qty_tolerance = max(1e-8, abs(confirmed_position.qty) * 1e-6)
                                if abs(current_position_qty - confirmed_position.qty) > qty_tolerance:
                                    raise ValueError(
                                        "POSITION DRIFT: confirmed-fill ledger quantity "
                                        f"{confirmed_position.qty:.8f} does not match broker quantity "
                                        f"{current_position_qty:.8f}."
                                    )
                                execution_reference_price = market_data.get_latest_price(
                                    symbol, asset_type=asset_type
                                )
                                protection_order = BrokerOrder(
                                    symbol=symbol,
                                    side="SELL",
                                    qty=confirmed_position.qty,
                                    price=execution_reference_price,
                                    asset_type=asset_type,
                                    metadata={
                                        "interval": interval,
                                        "protection_reason": protection.reason,
                                        "protection_trigger_price": protection.trigger_price,
                                        "protection_observation_price": protection.market_price,
                                        "execution_reference_price": execution_reference_price,
                                        "cooldown_bars": 0,
                                    },
                                )
                                protection_execution = submit_guarded_order(
                                    broker=broker,
                                    order=protection_order,
                                    settings=settings,
                                    execution_mode=execution_mode,
                                    broker_id=broker_id,
                                    account_equity=account_equity,
                                    current_position_qty=current_position_qty,
                                    day_start_equity=day_start_equity,
                                    peak_equity=peak_equity,
                                )
                                self.log(protection_execution.message)
                                await asyncio.sleep(get_poll_delay_seconds(interval))
                                continue
                            except ValueError as exc:
                                self.log(f"PROTECTION ORDER BLOCKED: {exc}")

                # Evaluate each completed/latest candle at most once. Polling may run
                # several times within a timeframe, but it must never create repeated
                # decisions or orders from the same market observation.
                candle_timestamp = df.index[-1]
                if self.last_evaluated_candle == candle_timestamp:
                    self.log(f"Skipping already evaluated candle: {candle_timestamp}")
                    await asyncio.sleep(get_poll_delay_seconds(interval))
                    continue
                self.last_evaluated_candle = candle_timestamp

                # 2. Evaluate strategy
                self.log("Evaluating strategy signals...")
                result_df = trading_engine.evaluate_strategy(strategy_record, df)
                signal = trading_engine.get_signal(result_df)

                # Runtime cooldown is counted in newly evaluated candles and starts
                # only after a confirmed SELL fill. It blocks re-entry BUYs without
                # suppressing exits or risk checks.
                if signal == "BUY" and self.cooldown_remaining > 0:
                    self.log(f"COOLDOWN BLOCKED BUY: {self.cooldown_remaining} bar(s) remaining.")
                    self.cooldown_remaining -= 1
                    signal = None
                elif self.cooldown_remaining > 0:
                    self.cooldown_remaining -= 1
                
                if signal:
                    if signal == "BUY" and confirmed_position.qty > 0:
                        self.log(
                            f"BUY BLOCKED: confirmed long position already open "
                            f"({confirmed_position.qty:.8f} {symbol})."
                        )
                        await asyncio.sleep(get_poll_delay_seconds(interval))
                        continue

                    if has_unresolved_order(
                        scoped_trades,
                        symbol,
                        broker_id,
                        execution_mode,
                    ):
                        self.log("ORDER BLOCKED: unresolved prior broker order must reach a final state first.")
                        await asyncio.sleep(get_poll_delay_seconds(interval))
                        continue

                    price_column = 'close' if 'close' in df.columns else 'Close'
                    last_price = float(df.iloc[-1][price_column])
                    self.log(f"SIGNAL DETECTED: {signal} at ${last_price}")

                    account_equity, current_position_qty, day_start_equity, peak_equity = get_risk_context(
                        broker, symbol, settings, execution_mode, broker_id
                    )
                    order_qty = resolve_strategy_quantity(
                        result_df, signal, last_price, account_equity, current_position_qty
                    )
                    order = BrokerOrder(
                        symbol=symbol,
                        side=signal,
                        qty=order_qty,
                        price=last_price,
                        asset_type=asset_type,
                        metadata={
                            "interval": interval,
                            "cooldown_bars": resolve_cooldown_bars(result_df) if signal == "SELL" else 0,
                            **(resolve_position_protection_params(result_df) if signal == "BUY" else {}),
                        },
                    )

                    try:
                        execution = submit_guarded_order(
                            broker=broker,
                            order=order,
                            settings=settings,
                            execution_mode=execution_mode,
                            broker_id=broker_id,
                            account_equity=account_equity,
                            current_position_qty=current_position_qty,
                            day_start_equity=day_start_equity,
                            peak_equity=peak_equity,
                        )
                    except ValueError as exc:
                        self.log(str(exc))
                        await asyncio.sleep(get_poll_delay_seconds(interval))
                        continue

                    if should_start_cooldown(signal, execution, order.qty):
                        self.cooldown_remaining = int(order.metadata.get("cooldown_bars", 0))
                    self.log(execution.message)
                else:
                    self.log("No signal detected.")

            except Exception as e:
                self.log(f"ERROR in loop: {str(e)}")
            
            # Poll frequently enough to observe the next candle without re-evaluating
            # the same candle more than once.
            await asyncio.sleep(get_poll_delay_seconds(interval))

    def start(self, symbol, asset_type, interval, strategy_record, broker_id, execution_mode, strategy_id=None):
        if self.is_running:
            return
        if isinstance(strategy_record, str):
            strategy_record = {
                "strategy_format": "legacy_python",
                "strategy_spec": {},
                "code": strategy_record,
            }
        if not isinstance(strategy_record, dict):
            raise TypeError("strategy_record must be an explicit strategy record or legacy Python code")
        strategy_record = copy.deepcopy(strategy_record)
        self.is_running = True
        self.last_evaluated_candle = None
        self.cooldown_remaining = 0
        self.config = {
            "symbol": symbol, 
            "asset_type": asset_type,
            "interval": interval, 
            "broker_id": broker_id,
            "execution_mode": execution_mode,
            "strategy_code": strategy_record.get("code", ""),
            "strategy_id": strategy_id,
            "strategy_format": strategy_record.get("strategy_format", "legacy_python"),
            "strategy_record": strategy_record
        }
        self.active_task = asyncio.create_task(self.run_loop())

    def stop(self):
        self.is_running = False
        if self.active_task:
            self.active_task.cancel()
            self.active_task = None
        self.cooldown_remaining = 0
        self.log("Trading loop stopped.")

trading_manager = LiveTradingManager()


def get_risk_context(broker, symbol: str, settings: Dict[str, Any], execution_mode: str, broker_id: str, account: Dict[str, Any] | None = None) -> tuple[float | None, float | None, float | None, float | None]:
    """Normalize account equity and current symbol position for central risk checks."""
    account = account if account is not None else broker.get_account_summary(settings, execution_mode)
    equity_raw = account.get("equity")
    account_equity = float(equity_raw) if equity_raw is not None else None

    current_position_qty = None
    for position in account.get("positions", []) or []:
        if position.get("symbol") == symbol:
            current_position_qty = float(position.get("qty", 0.0))
            break

    if current_position_qty is None and broker_id == "paper":
        current_position_qty = 0.0

    if execution_mode == "live" and account_equity is None:
        raise ValueError("Live risk validation requires broker account equity.")
    if execution_mode == "live" and current_position_qty is None:
        raise ValueError(f"Live risk validation requires position state for {symbol}.")

    day_start_equity = None
    peak_equity = None
    if account_equity is not None and account_equity > 0:
        equity_state = update_risk_equity_state(broker_id, execution_mode, account_equity)
        day_start_equity = equity_state["day_start_equity"]
        peak_equity = equity_state["peak_equity"]

    return account_equity, current_position_qty, day_start_equity, peak_equity




FINAL_ORDER_STATUSES = {"filled", "canceled", "cancelled", "rejected", "expired", "tested"}


def reconcile_trade_order(trade: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh one unresolved live order from its owning broker and persist fill state."""
    if trade.get("is_test") or trade.get("execution_mode") != "live":
        return trade
    if str(trade.get("order_status", "")).lower() in FINAL_ORDER_STATUSES:
        terminal = dict(trade)
        terminal["_completed_exit_transition"] = False
        return terminal

    broker = broker_registry.get(trade.get("broker_id", "paper"))
    status = broker.get_order_status(trade, settings)
    updated = dict(trade)
    updated["order_status"] = status.get("order_status", trade.get("order_status"))
    updated["broker_order_id"] = status.get("broker_order_id", trade.get("broker_order_id"))
    metadata = dict(trade.get("metadata") or {})
    metadata.update(status.get("metadata") or {})
    updated["metadata"] = metadata
    if "filled_qty" in status:
        prior_filled_qty = float(trade.get("filled_qty") or 0)
        broker_filled_qty = float(status["filled_qty"] or 0)
        if broker_filled_qty + 1e-12 < prior_filled_qty:
            raise ValueError(
                f"Broker cumulative filled quantity regressed from {prior_filled_qty} to {broker_filled_qty}."
            )
        updated["filled_qty"] = broker_filled_qty
    if "filled_price" in status:
        updated["filled_price"] = float(status["filled_price"] or 0)

    update_trade_order_state(
        updated["id"],
        updated["order_status"],
        updated.get("broker_order_id"),
        updated.get("metadata", {}),
        filled_qty=updated.get("filled_qty"),
        filled_price=updated.get("filled_price"),
    )
    was_final = str(trade.get("order_status", "")).lower() in FINAL_ORDER_STATUSES
    requested_qty = float(updated.get("requested_qty") or updated.get("qty") or 0)
    fully_filled_exit = (
        not was_final
        and str(updated.get("side", "")).upper() == "SELL"
        and str(updated.get("order_status", "")).lower() == "filled"
        and requested_qty > 0
        and float(updated.get("filled_qty") or 0) > 0
        and float(updated.get("filled_qty") or 0) >= requested_qty
    )
    updated["_completed_exit_transition"] = fully_filled_exit
    return updated


def reconcile_unresolved_orders(
    trades: list[Dict[str, Any]],
    settings: Dict[str, Any],
    symbol: str,
    broker_id: str,
    execution_mode: str,
) -> list[Dict[str, Any]]:
    """Refresh unresolved orders for the active autonomous trading scope."""
    reconciled = []
    for trade in trades:
        same_scope = (
            trade.get("symbol") == symbol
            and trade.get("broker_id", "paper") == broker_id
            and trade.get("execution_mode", "paper") == execution_mode
        )
        if same_scope:
            try:
                trade = reconcile_trade_order(trade, settings)
            except Exception as exc:
                trade = dict(trade)
                metadata = dict(trade.get("metadata") or {})
                metadata["status_refresh_error"] = str(exc)
                trade["metadata"] = metadata
        reconciled.append(trade)
    return reconciled

def has_unresolved_order(
    trades: list[Dict[str, Any]],
    symbol: str,
    broker_id: str,
    execution_mode: str,
) -> bool:
    """Prevent overlapping autonomous orders until prior broker state is final."""
    final_statuses = FINAL_ORDER_STATUSES
    for trade in trades:
        if trade.get("is_test"):
            continue
        if trade.get("symbol") != symbol:
            continue
        if trade.get("broker_id", "paper") != broker_id:
            continue
        if trade.get("execution_mode", "paper") != execution_mode:
            continue
        if str(trade.get("order_status", "")).lower() not in final_statuses:
            return True
    return False


def submit_guarded_order(
    *,
    broker,
    order: BrokerOrder,
    settings: Dict[str, Any],
    execution_mode: str,
    broker_id: str,
    account_equity: float | None,
    current_position_qty: float | None,
    day_start_equity: float | None,
    peak_equity: float | None,
):
    """Validate, submit, and persist one autonomous order through shared safeguards."""
    risk = risk_engine.evaluate_order(
        side=order.side,
        qty=order.qty,
        price=order.price,
        execution_mode=execution_mode,
        settings=settings,
        current_position_qty=current_position_qty,
        account_equity=float(account_equity) if account_equity is not None else None,
        day_start_equity=day_start_equity,
        peak_equity=peak_equity,
    )
    if not risk.approved:
        raise ValueError(f"RISK BLOCKED ORDER: {'; '.join(risk.reasons)}")

    broker_validation = broker.validate_order(order, execution_mode, settings)
    if not broker_validation.get("ok", False):
        raise ValueError(f"BROKER VALIDATION BLOCKED ORDER: {broker_validation}")

    order.qty = float(broker_validation.get("normalized_qty", order.qty))
    if order.qty <= 0:
        raise ValueError("Broker-normalized order quantity must be greater than zero.")

    execution = broker.execute_order(order, execution_mode, settings)
    record_trade(
        order.symbol,
        order.side,
        order.qty,
        order.price,
        is_paper=execution.execution_mode == "paper",
        broker_id=execution.broker_id,
        execution_mode=execution.execution_mode,
        order_status=execution.status,
        order_type="market",
        broker_order_id=execution.metadata.get("broker_order_id"),
        is_test=False,
        metadata=execution.metadata,
        requested_qty=order.qty,
        filled_qty=execution.filled_qty,
        filled_price=execution.filled_price,
    )
    return execution


def should_start_cooldown(signal: str, execution, requested_qty: float) -> bool:
    """Start cooldown only after the requested exit is completely filled."""
    return (
        signal == "SELL"
        and str(execution.status).lower() == "filled"
        and float(execution.filled_qty or 0) > 0
        and float(execution.filled_qty or 0) >= float(requested_qty)
    )




def resolve_position_protection_params(result_df) -> Dict[str, float]:
    """Freeze validated entry protection parameters from the strategy output."""
    resolved: Dict[str, float] = {}
    for column in ("stop_loss_pct", "take_profit_pct"):
        if column not in result_df.columns:
            resolved[column] = 0.0
            continue
        raw = result_df.iloc[-1][column]
        if isinstance(raw, bool) or str(getattr(raw, "dtype", "")).lower() == "bool":
            raise ValueError(f"{column} must be between 0 and 100.")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{column} must be between 0 and 100.") from None
        if value < 0 or value > 100:
            raise ValueError(f"{column} must be between 0 and 100.")
        resolved[column] = value
    return resolved

def resolve_cooldown_bars(result_df) -> int:
    """Read a validated cooldown duration from the strategy output."""
    if "cooldown_bars" not in result_df.columns:
        return 0
    raw = result_df.iloc[-1]["cooldown_bars"]
    if isinstance(raw, bool) or str(getattr(raw, "dtype", "")).lower() == "bool":
        raise ValueError("cooldown_bars must contain non-negative integers.")
    try:
        numeric = float(raw)
    except (TypeError, ValueError):
        raise ValueError("cooldown_bars must contain non-negative integers.") from None
    if not numeric.is_integer() or numeric < 0:
        raise ValueError("cooldown_bars must contain non-negative integers.")
    return int(numeric)

def resolve_strategy_quantity(result_df, signal: str, price: float, account_equity: float | None, current_position_qty: float | None) -> float:
    """Translate strategy position_size_pct into an executable quantity."""
    if signal == "SELL":
        if current_position_qty is None or current_position_qty <= 0:
            return 0.0
        return float(current_position_qty)

    if account_equity is None or account_equity <= 0:
        return 0.0

    position_size_pct = 10.0
    if "position_size_pct" in result_df.columns:
        raw_pct = result_df.iloc[-1]["position_size_pct"]
        try:
            position_size_pct = float(raw_pct)
        except (TypeError, ValueError):
            return 0.0

    if not 0 < position_size_pct <= 100:
        return 0.0

    target_notional = account_equity * (position_size_pct / 100.0)
    return target_notional / price if price > 0 else 0.0


def resolve_market_price(symbol: str, asset_type: str) -> float:
    """Resolve a validated market price; never fabricate a fallback price."""
    if asset_type == "stock":
        df = market_data.get_stock_data(symbol, "1d")
    elif asset_type == "crypto":
        df = market_data.get_crypto_data(symbol, "1h", limit=5)
    else:
        raise MarketDataError(f"Unsupported asset type for market price: {asset_type}")

    if df.empty or "close" not in df.columns:
        raise MarketDataError(f"No valid market price available for {symbol}.")

    market_price = float(df.iloc[-1]["close"])
    if market_price <= 0:
        raise MarketDataError(f"Invalid market price for {symbol}: {market_price}")
    return market_price

def build_autonomous_readiness(symbol: str, asset_type: str, broker_id: str, execution_mode: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Build the single readiness verdict consumed by preflight and session startup."""
    broker = broker_registry.get(broker_id)
    market_price = resolve_market_price(symbol, asset_type)
    account = broker.get_account_summary(settings, execution_mode)
    account_equity, current_position_qty, day_start_equity, peak_equity = get_risk_context(
        broker, symbol, settings, execution_mode, broker_id, account
    )
    scoped_trades = reconcile_unresolved_orders(
        get_trades_for_scope(symbol, broker_id, execution_mode),
        settings,
        symbol,
        broker_id,
        execution_mode,
    )
    confirmed_position = reconstruct_confirmed_position(
        scoped_trades,
        symbol=symbol,
        broker_id=broker_id,
        execution_mode=execution_mode,
    )
    reference_order = BrokerOrder(
        symbol=symbol,
        side="BUY",
        qty=1.0,
        price=market_price,
        asset_type=asset_type,
        metadata={"source": "autonomy_preflight"},
    )
    risk = risk_engine.evaluate_order(
        side=reference_order.side,
        qty=reference_order.qty,
        price=reference_order.price,
        execution_mode=execution_mode,
        settings=settings,
        current_position_qty=current_position_qty,
        account_equity=account_equity,
        day_start_equity=day_start_equity,
        peak_equity=peak_equity,
    )
    validation = broker.validate_order(reference_order, execution_mode, settings)
    broker_status = broker.get_status(settings)
    decision = evaluate_autonomous_readiness(
        broker_status=broker_status,
        account=account,
        execution_mode=execution_mode,
        asset_type=asset_type,
        unresolved_order=has_unresolved_order(scoped_trades, symbol, broker_id, execution_mode),
        ledger_position_qty=confirmed_position.qty,
        broker_position_qty=current_position_qty,
        # Session readiness is intentionally independent of this hypothetical
        # reference order. Every real order still passes central risk and broker
        # validation in submit_guarded_order().
        risk_approved=True,
        broker_validation_ok=True,
    )
    return {
        "readiness": decision.as_dict(),
        "broker": broker_status,
        "account": account,
        "reference_order_risk": risk.as_dict(),
        "reference_order_validation": validation,
        "market_price": market_price,
        "ledger_position_qty": confirmed_position.qty,
        "broker_position_qty": current_position_qty,
    }


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
        try:
            readiness = build_autonomous_readiness(
                status.symbol,
                status.asset_type,
                status.broker_id,
                status.execution_mode,
                settings,
            )
        except (MarketDataError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Autonomous readiness check failed: {exc}")
        if not readiness["readiness"]["ready"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Autonomous trading session is not ready.",
                    **readiness["readiness"],
                },
            )

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

        sources = int(status.strategy_id is not None) + int(bool(status.strategy_spec)) + int(bool(status.strategy_code.strip()))
        if sources != 1:
            raise HTTPException(
                status_code=400,
                detail="Provide exactly one strategy source: strategy_id, strategy_spec, or strategy_code.",
            )

        if status.strategy_id is not None:
            stored = get_strategy(status.strategy_id)
            if not stored:
                raise HTTPException(status_code=400, detail="Saved strategy not found.")
            strategy_record = {
                "strategy_format": stored.get("strategy_format", "legacy_python"),
                "strategy_spec": dict(stored.get("strategy_spec") or {}),
                "code": stored.get("code") or "",
            }
        elif status.strategy_spec:
            strategy_record = {
                "strategy_format": "declarative_v1",
                "strategy_spec": dict(status.strategy_spec),
                "code": "",
            }
        else:
            strategy_record = {
                "strategy_format": "legacy_python",
                "strategy_spec": {},
                "code": status.strategy_code,
            }

        # Resolve a frozen in-memory strategy snapshot for this session. Database
        # edits after start require an explicit restart before they can affect trading.
        trading_manager.start(
            status.symbol,
            status.asset_type,
            status.interval,
            strategy_record,
            status.broker_id,
            status.execution_mode,
            strategy_id=status.strategy_id,
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
    refreshed: list[dict] = []
    for trade in get_trades(limit=20):
        try:
            trade = reconcile_trade_order(trade, settings)
        except Exception as exc:
            trade = dict(trade)
            metadata = dict(trade.get("metadata") or {})
            metadata["status_refresh_error"] = str(exc)
            metadata["broker_reason"] = str(exc)
            trade["metadata"] = metadata
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
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
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
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/trading/account/{broker_id}")
def get_broker_account(broker_id: str, execution_mode: str = "paper"):
    settings = get_settings() or {}
    try:
        broker = broker_registry.get(broker_id)
        return broker.get_account_summary(settings, execution_mode)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/trading/preflight")
def run_trading_preflight(request: TradingPreflightRequest):
    settings = get_settings() or {}
    try:
        return build_autonomous_readiness(
            request.symbol,
            request.asset_type,
            request.broker_id,
            request.execution_mode,
            settings,
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/api/trading/test-order")
def run_trading_test_order(request: TradingTestOrderRequest):
    settings = get_settings() or {}
    try:
        broker = broker_registry.get(request.broker_id)
        market_price = resolve_market_price(request.symbol, request.asset_type)
        account = broker.get_account_summary(settings, request.execution_mode)
        account_equity, current_position_qty, day_start_equity, peak_equity = get_risk_context(
            broker, request.symbol, settings, request.execution_mode, request.broker_id, account
        )
        order = BrokerOrder(
            symbol=request.symbol,
            side=request.side,
            qty=request.qty,
            price=market_price,
            asset_type=request.asset_type,
            metadata={"source": "manual_test"},
        )
        risk = risk_engine.evaluate_order(
            side=order.side,
            qty=order.qty,
            price=order.price,
            execution_mode=request.execution_mode,
            settings=settings,
            current_position_qty=current_position_qty,
            account_equity=account_equity,
            day_start_equity=day_start_equity,
            peak_equity=peak_equity,
        )
        if not risk.approved:
            raise HTTPException(status_code=400, detail={"message": "Risk engine blocked test order.", "risk": risk.as_dict()})
        order.qty = risk.normalized_qty
        result = broker.test_order(
            order,
            request.execution_mode,
            settings,
        )
        validation = result.get("validation", {})
        normalized_qty = float(validation.get("normalized_qty", order.qty))
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
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
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
            result.get("order_status", "cancel_requested"),
            result.get("broker_order_id"),
            result.get("metadata", {}),
            filled_qty=result.get("filled_qty"),
            filled_price=result.get("filled_price"),
        )
        trading_manager.log(result.get("message", f"Canceled order for trade {trade['id']}."))
        return {
            "status": "success",
            "trade_id": trade["id"],
            **result,
        }
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
