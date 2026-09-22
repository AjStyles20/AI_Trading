import pytest
import pandas as pd
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.data_service import market_data

def test_get_stock_data_graceful_failure():
    # We patch yfinance Ticker internally so that history() throws an exception
    # simulating the known NoneType bug
    with patch("core.data_service.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.side_effect = TypeError("'NoneType' object is not subscriptable")
        mock_ticker.return_value = mock_instance
        
        df = market_data.get_stock_data("FAKE", "1d", "1y")
        
        # Must return an empty DataFrame, not crash
        assert isinstance(df, pd.DataFrame)
        assert df.empty

def test_get_crypto_data_graceful_failure():
    # We patch yfinance Ticker internally so that history() throws an exception
    with patch("core.data_service.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.side_effect = Exception("Simulated Network Error")
        mock_ticker.return_value = mock_instance
        
        df = market_data.get_crypto_data("FAKE/USDT", "1d")
        
        # Must return an empty DataFrame, not crash
        assert isinstance(df, pd.DataFrame)
        assert df.empty
