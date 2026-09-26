import pytest

from backend.trading_api import get_poll_delay_seconds


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        ("1m", 15),
        ("5m", 75),
        ("15m", 225),
        ("30m", 300),
        ("1h", 300),
        ("4h", 300),
        ("1d", 300),
    ],
)
def test_poll_delay_is_timeframe_aware_and_bounded(interval, expected):
    assert get_poll_delay_seconds(interval) == expected


def test_poll_delay_rejects_unknown_interval():
    with pytest.raises(ValueError, match="Unsupported trading interval"):
        get_poll_delay_seconds("2h")



def test_manager_resets_candle_dedup_state_on_start(monkeypatch):
    import asyncio
    from backend.trading_api import LiveTradingManager

    manager = LiveTradingManager()
    manager.last_evaluated_candle = "old-candle"

    class DummyTask:
        pass

    monkeypatch.setattr(asyncio, "create_task", lambda coro: (coro.close(), DummyTask())[1])
    manager.start("BTC/USDT", "crypto", "1h", "def strategy(df): return df", "paper", "paper")

    assert manager.last_evaluated_candle is None
    assert manager.is_running is True


def test_manager_initial_dedup_state_is_empty():
    from backend.trading_api import LiveTradingManager

    manager = LiveTradingManager()
    assert manager.last_evaluated_candle is None
