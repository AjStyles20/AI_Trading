from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_service import market_data
from core.strategy_validator import strategy_validator

router = APIRouter()


class ValidationRequest(BaseModel):
    symbol: str
    asset_type: str = "stock"
    interval: str = "1h"
    period: str = "6mo"
    strategy_code: str


@router.post("/api/strategy/validate")
def validate_strategy(request: ValidationRequest):
    try:
        if request.asset_type == "stock":
            df = market_data.get_stock_data(request.symbol, request.interval, request.period)
        else:
            df = market_data.get_crypto_data(request.symbol, request.interval)

        if df.empty:
            raise ValueError("No market data available for validation.")

        df.columns = [column.lower() for column in df.columns]
        result = strategy_validator.validate(request.strategy_code, df)
        result["scenario"] = {
            "symbol": request.symbol,
            "asset_type": request.asset_type,
            "interval": request.interval,
            "period": request.period,
        }
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
