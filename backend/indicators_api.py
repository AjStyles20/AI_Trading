from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.indicators import (
    calculate_sma, calculate_ema, calculate_rsi, 
    calculate_macd, calculate_bollinger_bands, calculate_atr
)

router = APIRouter()

class OHLCVData(BaseModel):
    closes: List[float]
    highs: List[float] = []
    lows: List[float] = []
    period: int = 14

@router.post("/api/indicators/sma")
def get_sma(data: OHLCVData):
    return {"sma": calculate_sma(data.closes, data.period)}

@router.post("/api/indicators/ema")
def get_ema(data: OHLCVData):
    return {"ema": calculate_ema(data.closes, data.period)}

@router.post("/api/indicators/rsi")
def get_rsi(data: OHLCVData):
    return {"rsi": calculate_rsi(data.closes, data.period)}

@router.post("/api/indicators/macd")
def get_macd(data: OHLCVData):
    return calculate_macd(data.closes)

@router.post("/api/indicators/bollinger")
def get_bollinger(data: OHLCVData):
    return calculate_bollinger_bands(data.closes, data.period)

@router.post("/api/indicators/atr")
def get_atr(data: OHLCVData):
    return {"atr": calculate_atr(data.highs, data.lows, data.closes, data.period)}
