from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.backtest_engine import backtest_engine
from core.data_service import market_data
from core.strategy_validator import strategy_validator

router = APIRouter()


class BacktestRequest(BaseModel):
    symbol: str
    asset_type: str = "stock"
    interval: str = "1d"
    period: str = "1y"
    initial_balance: float = 10000.0
    fee_pct: float = 0.1
    slippage_pct: float = 0.05
    strategy_code: str


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

        local_scope = {"df": df.copy(), "pd": pd}
        exec(request.strategy_code, local_scope)

        if 'strategy' in local_scope:
            df_result = local_scope['strategy'](df.copy())
        else:
            df_result = local_scope.get('df')

        if isinstance(df_result, pd.Series):
            signal_series = df_result
            if len(signal_series) != len(df):
                raise ValueError("strategy(df) returned a signal series with a different length than the input data.")
            df_result = df.copy()
            df_result["signal"] = signal_series

        validation = strategy_validator.validate(request.strategy_code, df)
        if not validation["valid"]:
            raise ValueError("; ".join(validation["errors"]))

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
        }

        if isinstance(results.get("trade_history"), list):
            for trade in results["trade_history"]:
                trade["timestamp"] = str(trade["timestamp"])

        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
