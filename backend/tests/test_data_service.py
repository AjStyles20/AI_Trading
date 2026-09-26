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



def _frame_at(timestamp):
    import pandas as pd
    return pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp(timestamp)]),
    )


def test_crypto_freshness_rejects_stale_weekend_data():
    import pandas as pd
    frame = _frame_at("2026-09-26T10:00:00Z")
    with pytest.raises(MarketDataError, match="stale"):
        market_data.assert_fresh(
            frame, "1h", now=pd.Timestamp("2026-09-26T14:00:01Z"), asset_type="crypto"
        )


def test_stock_freshness_allows_friday_candle_during_weekend():
    import pandas as pd
    frame = _frame_at("2026-09-25T20:00:00Z")
    market_data.assert_fresh(
        frame, "1h", now=pd.Timestamp("2026-09-26T14:00:00Z"), asset_type="stock"
    )


def test_stock_freshness_rejects_stale_same_weekday_data():
    import pandas as pd
    frame = _frame_at("2026-09-25T10:00:00Z")
    with pytest.raises(MarketDataError, match="stale"):
        market_data.assert_fresh(
            frame, "1h", now=pd.Timestamp("2026-09-25T14:00:01Z"), asset_type="stock"
        )


def test_freshness_rejects_future_timestamp():
    import pandas as pd
    frame = _frame_at("2026-09-26T14:01:00Z")
    with pytest.raises(MarketDataError, match="future"):
        market_data.assert_fresh(
            frame, "1m", now=pd.Timestamp("2026-09-26T14:00:00Z"), asset_type="crypto"
        )


def test_freshness_rejects_unsupported_asset_type():
    import pandas as pd
    frame = _frame_at("2026-09-26T14:00:00Z")
    with pytest.raises(MarketDataError, match="Unsupported asset type"):
        market_data.assert_fresh(
            frame, "1m", now=pd.Timestamp("2026-09-26T14:00:30Z"), asset_type="forex"
        )
