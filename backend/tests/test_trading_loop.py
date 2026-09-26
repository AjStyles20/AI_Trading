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



@pytest.mark.parametrize(
    ("signal", "status", "filled_qty", "requested_qty", "expected"),
    [
        ("SELL", "filled", 1.0, 1.0, True),
        ("SELL", "filled", 0.5, 1.0, False),
        ("SELL", "partially_filled", 0.5, 1.0, False),
        ("SELL", "pending", 0.0, 1.0, False),
        ("SELL", "rejected", 0.0, 1.0, False),
        ("SELL", "canceled", 0.0, 1.0, False),
        ("BUY", "filled", 1.0, 1.0, False),
    ],
)
def test_cooldown_starts_only_after_complete_sell_fill(
    signal, status, filled_qty, requested_qty, expected
):
    from types import SimpleNamespace
    from backend.trading_api import should_start_cooldown

    execution = SimpleNamespace(status=status, filled_qty=filled_qty)
    assert should_start_cooldown(signal, execution, requested_qty) is expected



@pytest.mark.parametrize(
    ("status", "is_test", "symbol", "broker_id", "execution_mode", "expected"),
    [
        ("pending", False, "BTC/USDT", "binance", "live", True),
        ("partially_filled", False, "BTC/USDT", "binance", "live", True),
        ("submitted", False, "BTC/USDT", "binance", "live", True),
        ("filled", False, "BTC/USDT", "binance", "live", False),
        ("canceled", False, "BTC/USDT", "binance", "live", False),
        ("rejected", False, "BTC/USDT", "binance", "live", False),
        ("pending", True, "BTC/USDT", "binance", "live", False),
        ("pending", False, "ETH/USDT", "binance", "live", False),
        ("pending", False, "BTC/USDT", "bitget", "live", False),
        ("pending", False, "BTC/USDT", "binance", "paper", False),
    ],
)
def test_unresolved_order_guard_is_scoped_and_fail_closed(
    status, is_test, symbol, broker_id, execution_mode, expected
):
    from backend.trading_api import has_unresolved_order

    trades = [{
        "order_status": status,
        "is_test": is_test,
        "symbol": symbol,
        "broker_id": broker_id,
        "execution_mode": execution_mode,
    }]
    assert has_unresolved_order(trades, "BTC/USDT", "binance", "live") is expected



def test_reconcile_trade_order_persists_partial_fill(monkeypatch):
    import backend.trading_api as trading_api

    trade = {
        "id": 9, "symbol": "BTC/USDT", "broker_id": "binance",
        "execution_mode": "live", "order_status": "pending",
        "broker_order_id": "abc", "metadata": {}, "filled_qty": 0.0,
        "filled_price": 0.0, "is_test": False,
    }
    class Broker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "partially_filled",
                "broker_order_id": "abc",
                "metadata": {"source": "broker"},
                "filled_qty": 0.4,
                "filled_price": 101.5,
            }

    persisted = {}
    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(
        trading_api, "update_trade_order_state",
        lambda trade_id, status, broker_order_id, metadata, filled_qty=None, filled_price=None:
            persisted.update(id=trade_id, status=status, filled_qty=filled_qty, filled_price=filled_price),
    )

    updated = trading_api.reconcile_trade_order(trade, {})
    assert updated["order_status"] == "partially_filled"
    assert updated["filled_qty"] == 0.4
    assert updated["filled_price"] == 101.5
    assert persisted == {"id": 9, "status": "partially_filled", "filled_qty": 0.4, "filled_price": 101.5}


def test_reconcile_trade_order_skips_terminal_order(monkeypatch):
    import backend.trading_api as trading_api

    trade = {"id": 1, "order_status": "filled", "execution_mode": "live", "is_test": False}
    monkeypatch.setattr(
        trading_api.broker_registry, "get",
        lambda broker_id: (_ for _ in ()).throw(AssertionError("terminal order must not query broker")),
    )
    assert trading_api.reconcile_trade_order(trade, {}) is trade


def test_reconcile_unresolved_orders_keeps_refresh_failure_unresolved(monkeypatch):
    import backend.trading_api as trading_api

    trade = {
        "id": 2, "symbol": "BTC/USDT", "broker_id": "binance",
        "execution_mode": "live", "order_status": "pending",
        "metadata": {}, "is_test": False,
    }
    monkeypatch.setattr(
        trading_api, "reconcile_trade_order",
        lambda trade, settings: (_ for _ in ()).throw(RuntimeError("broker unavailable")),
    )
    updated = trading_api.reconcile_unresolved_orders(
        [trade], {}, "BTC/USDT", "binance", "live"
    )
    assert updated[0]["order_status"] == "pending"
    assert updated[0]["metadata"]["status_refresh_error"] == "broker unavailable"
    assert trading_api.has_unresolved_order(updated, "BTC/USDT", "binance", "live") is True
