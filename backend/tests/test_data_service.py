import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.data_service import MarketDataError, market_data


def test_get_stock_data_fails_closed_on_provider_error():
    with patch("core.data_service.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.side_effect = TypeError("'NoneType' object is not subscriptable")
        mock_ticker.return_value = mock_instance
        with pytest.raises(MarketDataError, match="Failed to fetch stock data"):
            market_data.get_stock_data("FAKE", "1d", "1y")


def test_get_crypto_data_fails_closed_on_provider_error():
    with patch("core.data_service.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.side_effect = Exception("Simulated Network Error")
        mock_ticker.return_value = mock_instance
        with pytest.raises(MarketDataError, match="Failed to fetch crypto data"):
            market_data.get_crypto_data("FAKE/USDT", "1d")
