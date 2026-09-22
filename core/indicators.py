import pandas as pd
import numpy as np
from typing import List

def calculate_sma(prices: List[float], period: int = 20) -> List[float | None]:
    """Simple Moving Average."""
    series = pd.Series(prices)
    return series.rolling(window=period).mean().tolist()

def calculate_ema(prices: List[float], period: int = 20) -> List[float | None]:
    """Exponential Moving Average."""
    series = pd.Series(prices)
    return series.ewm(span=period, adjust=False).mean().tolist()

def calculate_rsi(prices: List[float], period: int = 14) -> List[float | None]:
    """Relative Strength Index (0-100)."""
    series = pd.Series(prices)
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.tolist()

def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, Signal line, and Histogram."""
    series = pd.Series(prices)
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {
        "macd": macd_line.tolist(),
        "signal": signal_line.tolist(),
        "histogram": histogram.tolist(),
    }

def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0):
    """Bollinger Bands: Upper, Middle (SMA), Lower."""
    series = pd.Series(prices)
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return {
        "upper": upper.tolist(),
        "middle": middle.tolist(),
        "lower": lower.tolist(),
    }

def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float | None]:
    """Average True Range."""
    high = pd.Series(highs)
    low = pd.Series(lows)
    close = pd.Series(closes)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(window=period).mean().tolist()
