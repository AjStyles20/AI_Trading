from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.data_service import MarketDataError, market_data

router = APIRouter()

class DataRequest(BaseModel):
    symbol: str
    asset_type: str = "stock" # "stock" or "crypto"
    interval: str = "1d"
    period: Optional[str] = None
    limit: int = 500

@router.get("/api/market/price/{asset_type}/{symbol}")
def get_price(asset_type: str, symbol: str):
    try:
        price = market_data.get_latest_price(symbol, asset_type)
        return {"symbol": symbol, "price": price}
    except MarketDataError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/market/history")
def get_history(request: DataRequest):
    try:
        print(f"DEBUG: history request: {request}")
        if request.asset_type == "stock":
            df = market_data.get_stock_data(request.symbol, request.interval, request.period)
        elif request.asset_type == "crypto":
            df = market_data.get_crypto_data(request.symbol, request.interval, request.limit)
        else:
            raise ValueError("asset_type must be stock or crypto")
        
        # Convert index to UTC Unix milliseconds for unambiguous frontend parsing.
        # numpy int64 on a DatetimeIndex gives nanoseconds since epoch; divide by 10^6 for ms.
        import numpy as np
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_convert('UTC').tz_localize(None)
        df.index = df.index.view(np.int64) // 10**6  # nanoseconds -> milliseconds
        df.index.name = 'timestamp'
        return df.reset_index().to_dict(orient="records")
    except MarketDataError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
