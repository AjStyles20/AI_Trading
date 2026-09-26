import pandas as pd
import pytest

from core.data_service import MarketDataError, MarketDataService


def _frame():
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 11.0],
        },
        index=pd.DatetimeIndex([
            pd.Timestamp("2026-09-26T13:00:00Z"),
            pd.Timestamp("2026-09-26T14:00:00Z"),
        ]),
    )


def test_completed_candles_excludes_forming_interval_before_close():
    service = MarketDataService()
    completed = service.get_completed_candles(
        _frame(), "1h", now=pd.Timestamp("2026-09-26T14:59:59Z")
    )
    assert list(completed.index) == [pd.Timestamp("2026-09-26T13:00:00Z")]


def test_completed_candles_includes_interval_exactly_at_close():
    service = MarketDataService()
    completed = service.get_completed_candles(
        _frame(), "1h", now=pd.Timestamp("2026-09-26T15:00:00Z")
    )
    assert list(completed.index) == [
        pd.Timestamp("2026-09-26T13:00:00Z"),
        pd.Timestamp("2026-09-26T14:00:00Z"),
    ]


def test_completed_candles_rejects_when_no_interval_has_closed():
    service = MarketDataService()
    with pytest.raises(MarketDataError, match="no completed candles"):
        service.get_completed_candles(
            _frame().iloc[[0]], "1h", now=pd.Timestamp("2026-09-26T13:30:00Z")
        )
