import pandas as pd
import pytest

from core.data_service import MarketDataError, MarketDataService


def test_validate_frame_normalizes_sorts_and_deduplicates():
    svc = MarketDataService()
    idx = pd.to_datetime(["2026-01-02", "2026-01-01", "2026-01-01"])
    df = pd.DataFrame({
        "Open": [2, 1, 1.1], "High": [3, 2, 2.1], "Low": [1, .5, .6],
        "Close": [2.5, 1.5, 1.6], "Volume": [10, 20, 30],
    }, index=idx)
    out = svc._validate_frame(df, "TEST")
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out.index.is_monotonic_increasing
    assert not out.index.duplicated().any()
    assert len(out) == 2


def test_validate_frame_rejects_missing_ohlcv():
    svc = MarketDataService()
    df = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2026-01-01"]))
    with pytest.raises(MarketDataError):
        svc._validate_frame(df, "TEST")


def test_validate_frame_rejects_non_positive_price():
    svc = MarketDataService()
    df = pd.DataFrame({
        "open": [100], "high": [101], "low": [0], "close": [100], "volume": [1],
    }, index=pd.to_datetime(["2026-01-01"]))
    with pytest.raises(MarketDataError):
        svc._validate_frame(df, "TEST")
