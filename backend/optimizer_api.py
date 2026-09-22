from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_service import market_data
from core.strategy_optimizer import strategy_optimizer

router = APIRouter()


class OptimizationRequest(BaseModel):
    symbol: str
    asset_type: str = "stock"
    interval: str = "1h"
    period: str = "6mo"
    strategy_type: str = "ema_rsi"
    initial_balance: float = 10000.0
    fee_pct: float = 0.1
    slippage_pct: float = 0.05
    custom_ranges: Dict[str, List[int]] = {}


@router.post("/api/strategy/optimize")
def optimize_strategy(request: OptimizationRequest):
    try:
        if request.asset_type == "stock":
            df = market_data.get_stock_data(request.symbol, request.interval, request.period)
        else:
            df = market_data.get_crypto_data(request.symbol, request.interval)

        if df.empty:
            raise ValueError("No market data available for optimization.")

        df.columns = [column.lower() for column in df.columns]
        results = strategy_optimizer.optimize(
            df,
            strategy_type=request.strategy_type,
            custom_ranges=request.custom_ranges,
            initial_balance=request.initial_balance,
            fee_pct=request.fee_pct,
            slippage_pct=request.slippage_pct,
        )
        results["scenario"] = {
            "symbol": request.symbol,
            "asset_type": request.asset_type,
            "interval": request.interval,
            "period": request.period,
            "initial_balance": request.initial_balance,
            "fee_pct": request.fee_pct,
            "slippage_pct": request.slippage_pct,
            "custom_ranges": request.custom_ranges,
        }
        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
