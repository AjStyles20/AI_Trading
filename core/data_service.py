import yfinance as yf
import ccxt
import pandas as pd
from typing import Optional, List, Dict
import datetime


class MarketDataError(RuntimeError):
    pass

class MarketDataService:
    REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

    def _validate_frame(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if df is None or df.empty:
            raise MarketDataError(f"No market data returned for {symbol}.")
        normalized = df.copy()
        normalized.columns = [str(col).lower() for col in normalized.columns]
        missing = self.REQUIRED_COLUMNS.difference(normalized.columns)
        if missing:
            raise MarketDataError(f"Market data for {symbol} is missing columns: {sorted(missing)}")
        normalized = normalized[~normalized.index.duplicated(keep="last")].sort_index()
        normalized = normalized.dropna(subset=["open", "high", "low", "close"])
        if normalized.empty:
            raise MarketDataError(f"Market data for {symbol} contains no valid OHLC rows.")
        if (normalized[["open", "high", "low", "close"]] <= 0).any().any():
            raise MarketDataError(f"Market data for {symbol} contains non-positive prices.")
        normalized.index.name = "timestamp"
        return normalized

    def __init__(self):
        # We can expand this with more exchanges later
        self.binance = ccxt.binance()

    def _get_balanced_period(self, interval: str) -> str:
        """Helper to get a valid yfinance period for a given interval.
        Limits: 1m max 7d, 2m-15m max 60d, 1h-max 730d.
        """
        if interval == "1m":
            return "7d"
        if interval in ["5m", "15m"]:
            return "60d"
        if interval in ["1h", "4h"]:
            return "600d" # Safe limit for yfinance 1h/4h data
        return "1y" # default for 1d and others

    def assert_fresh(self, df: pd.DataFrame, interval: str, now: pd.Timestamp | None = None, asset_type: str = "crypto") -> None:
        if df is None or df.empty:
            raise MarketDataError("Cannot assess freshness of empty market data.")
        interval_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
        minutes = interval_minutes.get(interval)
        if minutes is None:
            raise MarketDataError(f"Unsupported interval for freshness validation: {interval}")
        latest = pd.Timestamp(df.index[-1])
        if latest.tzinfo is None:
            latest = latest.tz_localize("UTC")
        else:
            latest = latest.tz_convert("UTC")
        current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
        if current.tzinfo is None:
            current = current.tz_localize("UTC")
        else:
            current = current.tz_convert("UTC")
        max_age = pd.Timedelta(minutes=minutes * 3)
        age = current - latest
        if age < pd.Timedelta(0):
            raise MarketDataError("Latest market timestamp is in the future.")

        if asset_type == "stock":
            # A simple continuous-age rule is unsafe for exchange-traded assets:
            # Friday's final candle is expected to remain the latest throughout a weekend.
            # Until a broker/exchange calendar is integrated, only enforce the strict
            # intraday age limit while both timestamps fall on the same UTC weekday.
            same_calendar_day = latest.date() == current.date()
            weekday = current.weekday() < 5
            if not (same_calendar_day and weekday):
                return
        elif asset_type != "crypto":
            raise MarketDataError(f"Unsupported asset type for freshness validation: {asset_type}")

        if age > max_age:
            raise MarketDataError(
                f"Market data is stale: latest candle is {age} old; maximum allowed is {max_age}."
            )

    def get_stock_data(self, symbol: str, interval: str = "1d", period: str = None) -> pd.DataFrame:
        """Fetch historical stock data using yfinance."""
        if not period:
            period = self._get_balanced_period(interval)
        
        try:
            print(f"FETCH: Stock data for {symbol} ({interval}, {period})")
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            return self._validate_frame(df, symbol)
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(f"Failed to fetch stock data for {symbol}: {e}") from e

    def get_crypto_data(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        """Fetch historical crypto data bypassing ccxt Binance region blocks using yfinance."""
        try:
            yf_symbol = symbol.replace('/', '-').replace('USDT', 'USD')
            period = self._get_balanced_period(interval)
            
            print(f"FETCH: Crypto data for {yf_symbol} ({interval}, {period})")
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval)
            
            return self._validate_frame(df, symbol)
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(f"Failed to fetch crypto data for {symbol}: {e}") from e

    def get_latest_price(self, symbol: str, asset_type: str = "stock") -> float:
        """Get the most recent price for an asset."""
        try:
            query_symbol = symbol
            if asset_type == "crypto":
                query_symbol = symbol.replace('/', '-').replace('USDT', 'USD')
                
            ticker = yf.Ticker(query_symbol)
            history = ticker.history(period="1d")
            if history.empty or "Close" not in history:
                raise MarketDataError(f"No latest price available for {symbol}.")
            price = float(history["Close"].iloc[-1])
            if not pd.notna(price) or price <= 0:
                raise MarketDataError(f"Invalid latest price for {symbol}: {price}")
            return price
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(f"Failed to fetch latest price for {symbol}: {e}") from e

# Singleton instance
market_data = MarketDataService()
