import yfinance as yf
import ccxt
import pandas as pd
from typing import Optional, List, Dict
import datetime

class MarketDataService:
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

    def get_stock_data(self, symbol: str, interval: str = "1d", period: str = None) -> pd.DataFrame:
        """Fetch historical stock data using yfinance."""
        if not period:
            period = self._get_balanced_period(interval)
        
        try:
            print(f"FETCH: Stock data for {symbol} ({interval}, {period})")
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if not df.empty:
                df.index.name = 'timestamp'
            return df
        except Exception as e:
            print(f"CRITICAL ERROR in get_stock_data: {str(e)}")
            return pd.DataFrame()

    def get_crypto_data(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        """Fetch historical crypto data bypassing ccxt Binance region blocks using yfinance."""
        try:
            yf_symbol = symbol.replace('/', '-').replace('USDT', 'USD')
            period = self._get_balanced_period(interval)
            
            print(f"FETCH: Crypto data for {yf_symbol} ({interval}, {period})")
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print(f"WARNING: No data returned for {yf_symbol}")
                return pd.DataFrame()
            
            df.index.name = 'timestamp'
            return df
        except Exception as e:
            print(f"CRITICAL ERROR in get_crypto_data: {str(e)}")
            return pd.DataFrame()

    def get_latest_price(self, symbol: str, asset_type: str = "stock") -> float:
        """Get the most recent price for an asset."""
        try:
            query_symbol = symbol
            if asset_type == "crypto":
                query_symbol = symbol.replace('/', '-').replace('USDT', 'USD')
                
            ticker = yf.Ticker(query_symbol)
            return float(ticker.history(period="1d")['Close'].iloc[-1])
        except Exception as e:
            print(f"Error getting latest price: {e}")
            return 0.0

# Singleton instance
market_data = MarketDataService()
