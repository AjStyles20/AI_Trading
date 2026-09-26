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



@pytest.mark.asyncio
async def test_same_candle_is_evaluated_only_once(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.config = {
        "symbol": "BTC/USDT",
        "asset_type": "crypto",
        "interval": "1h",
        "broker_id": "paper",
        "execution_mode": "paper",
        "strategy_code": "def strategy(df): return df",
    }

    frame = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-26T12:00:00Z")]),
    )
    evaluations = {"count": 0}
    sleeps = {"count": 0}

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)

    def evaluate_strategy(code, df):
        evaluations["count"] += 1
        return df.assign(signal=0)

    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", evaluate_strategy)
    monkeypatch.setattr(trading_api.trading_engine, "get_signal", lambda df: None)

    async def controlled_sleep(seconds):
        sleeps["count"] += 1
        if sleeps["count"] >= 2:
            manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", controlled_sleep)

    await manager.run_loop()

    assert evaluations["count"] == 1
    assert manager.last_evaluated_candle == frame.index[-1]
    assert any("Skipping already evaluated candle" in entry for entry in manager.logs)



def test_manager_freezes_strategy_record_snapshot_on_start(monkeypatch):
    import asyncio
    from backend.trading_api import LiveTradingManager

    manager = LiveTradingManager()
    source = {
        "strategy_format": "declarative_v1",
        "strategy_spec": {
            "schema_version": 1,
            "strategy_type": "sma_cross",
            "params": {"sma_fast": 2, "sma_slow": 5},
        },
        "code": "",
    }

    class DummyTask:
        pass

    monkeypatch.setattr(asyncio, "create_task", lambda coro: (coro.close(), DummyTask())[1])
    manager.start("BTC/USDT", "crypto", "1h", source, "paper", "paper", strategy_id=7)

    source["strategy_spec"]["params"]["sma_fast"] = 99

    assert manager.config["strategy_id"] == 7
    assert manager.config["strategy_format"] == "declarative_v1"
    assert manager.config["strategy_record"]["strategy_spec"]["params"]["sma_fast"] == 2


def test_manager_normalizes_legacy_code_to_explicit_record(monkeypatch):
    import asyncio
    from backend.trading_api import LiveTradingManager

    manager = LiveTradingManager()

    class DummyTask:
        pass

    monkeypatch.setattr(asyncio, "create_task", lambda coro: (coro.close(), DummyTask())[1])
    manager.start("BTC/USDT", "crypto", "1h", "def strategy(df): return df", "paper", "paper")

    record = manager.config["strategy_record"]
    assert record["strategy_format"] == "legacy_python"
    assert record["strategy_spec"] == {}
    assert record["code"].startswith("def strategy")
