from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.backtest_engine import backtest_engine
from core.data_service import market_data
from core.strategy_validator import strategy_validator
from core.strategy_execution import execute_strategy_record
from database.sqlite_manager import get_strategy

router = APIRouter()


class BacktestRequest(BaseModel):
    symbol: str
    asset_type: str = "stock"
    interval: str = "1d"
    period: str = "1y"
    initial_balance: float = 10000.0
    fee_pct: float = 0.1
    slippage_pct: float = 0.05
    strategy_code: str = ""
    strategy_id: Optional[int] = None
    strategy_spec: Dict[str, Any] = {}


@router.post("/api/backtest/run")
def run_backtest(request: BacktestRequest):
    try:
        if request.asset_type == "stock":
            df = market_data.get_stock_data(request.symbol, request.interval, request.period)
        else:
            df = market_data.get_crypto_data(request.symbol, request.interval)

        if df is None or df.empty:
            raise ValueError("No market data returned for the requested symbol/interval/period.")

        df.columns = [column.lower() for column in df.columns]
        if "close" not in df.columns:
            for candidate in ("adj close", "adj_close", "closing", "price"):
                if candidate in df.columns:
                    df["close"] = df[candidate]
                    break

        if "close" not in df.columns:
            raise ValueError("Missing required 'close' column after normalization.")

        sources = int(request.strategy_id is not None) + int(bool(request.strategy_spec)) + int(bool(request.strategy_code.strip()))
        if sources != 1:
            raise ValueError("Provide exactly one strategy source: strategy_id, strategy_spec, or strategy_code.")

        if request.strategy_id is not None:
            strategy_record = get_strategy(request.strategy_id)
            if not strategy_record:
                raise ValueError("Saved strategy not found.")
        elif request.strategy_spec:
            strategy_record = {
                "strategy_format": "declarative_v1",
                "strategy_spec": request.strategy_spec,
                "code": "",
            }
        else:
            strategy_record = {
                "strategy_format": "legacy_python",
                "strategy_spec": {},
                "code": request.strategy_code,
            }

        df_result = execute_strategy_record(strategy_record, df)

        if strategy_record["strategy_format"] == "legacy_python":
            validation = strategy_validator.validate(strategy_record["code"], df)
            if not validation["valid"]:
                raise ValueError("; ".join(validation["errors"]))
        else:
            validation = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "strategy_format": "declarative_v1",
            }

        results = backtest_engine.run_backtest(
            df_result,
            initial_balance=request.initial_balance,
            fee_pct=request.fee_pct,
            slippage_pct=request.slippage_pct,
        )
        results["validation"] = validation
        results["scenario"] = {
            "symbol": request.symbol,
            "asset_type": request.asset_type,
            "interval": request.interval,
            "period": request.period,
            "initial_balance": request.initial_balance,
            "fee_pct": request.fee_pct,
            "slippage_pct": request.slippage_pct,
            "strategy_format": strategy_record["strategy_format"],
            "strategy_id": request.strategy_id,
        }

        if isinstance(results.get("trade_history"), list):
            for trade in results["trade_history"]:
                trade["timestamp"] = str(trade["timestamp"])

        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
