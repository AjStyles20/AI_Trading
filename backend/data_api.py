from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.data_service import MarketDataError, market_data
from backend.history_cache import HistoryCache

router = APIRouter()
# Shared by all open copies of the app; see backend/history_cache.py.
history_cache = HistoryCache()

class DataRequest(BaseModel):
    symbol: str
    asset_type: str = "stock" # "stock" or "crypto"
    interval: str = "1d"
    period: Optional[str] = None
    limit: int = Field(500, ge=1, le=5000)

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
            fetch = lambda: market_data.get_stock_data(request.symbol, request.interval, request.period)  # noqa: E731
        elif request.asset_type == "crypto":
            fetch = lambda: market_data.get_crypto_data(request.symbol, request.interval, request.limit)  # noqa: E731
        else:
            raise ValueError("asset_type must be stock or crypto")
        # The limit is applied below, per request, so it is not part of the key.
        key = (request.asset_type, request.symbol.strip().upper(), request.interval, request.period)
        df = history_cache.get_or_fetch(key, request.interval, fetch)

        # The provider returns a whole period (7 days of 1m candles is ~10k
        # rows, ~1.5 MB of JSON). Return only the most recent `limit` candles;
        # the chart polls this endpoint. The limit is applied here rather than in
        # the data service so the trading loop's history is unchanged.
        df = df.tail(request.limit)

        # Pandas 3 may store the index in seconds, while earlier versions
        # commonly use nanoseconds. Convert the unit explicitly before exposing
        # Unix milliseconds to the frontend.
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_convert('UTC').tz_localize(None)
        df.index = df.index.as_unit("ms").asi8
        df.index.name = 'timestamp'
        return df.reset_index().to_dict(orient="records")
    except MarketDataError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
