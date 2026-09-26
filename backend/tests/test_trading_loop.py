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
    reconciliations = {"count": 0}
    sleeps = {"count": 0}

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {})
    monkeypatch.setattr(trading_api, "get_trades", lambda limit=100: [])

    def reconcile(*args, **kwargs):
        reconciliations["count"] += 1
        return []

    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", reconcile)

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
    assert reconciliations["count"] == 2
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
    updated = trading_api.reconcile_trade_order(trade, {})
    assert updated is not trade
    assert updated["_completed_exit_transition"] is False


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



@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, 0), (2, 2), ("3", 3)],
)
def test_resolve_cooldown_bars_accepts_nonnegative_integers(raw, expected):
    import pandas as pd
    from backend.trading_api import resolve_cooldown_bars

    assert resolve_cooldown_bars(pd.DataFrame({"cooldown_bars": [raw]})) == expected


@pytest.mark.parametrize("raw", [-1, 1.5, True, "bad"])
def test_resolve_cooldown_bars_rejects_invalid_values(raw):
    import pandas as pd
    from backend.trading_api import resolve_cooldown_bars

    with pytest.raises(ValueError, match="non-negative integers"):
        resolve_cooldown_bars(pd.DataFrame({"cooldown_bars": [raw]}))


def test_reconciled_full_sell_marks_one_time_exit_transition(monkeypatch):
    import backend.trading_api as trading_api

    trade = {
        "id": 12, "symbol": "BTC/USDT", "side": "SELL", "qty": 1.0,
        "requested_qty": 1.0, "broker_id": "binance", "execution_mode": "live",
        "order_status": "partially_filled", "broker_order_id": "sell-12",
        "metadata": {"cooldown_bars": 2}, "filled_qty": 0.4,
        "filled_price": 100.0, "is_test": False,
    }
    class Broker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "filled", "broker_order_id": "sell-12",
                "metadata": {"cooldown_bars": 2}, "filled_qty": 1.0,
                "filled_price": 101.0,
            }

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *args, **kwargs: None)

    updated = trading_api.reconcile_trade_order(trade, {})
    assert updated["_completed_exit_transition"] is True

    already_final = dict(updated)
    again = trading_api.reconcile_trade_order(already_final, {})
    assert "_completed_exit_transition" in again
    assert again["_completed_exit_transition"] is False


def test_partial_sell_reconciliation_does_not_mark_completed_exit(monkeypatch):
    import backend.trading_api as trading_api

    trade = {
        "id": 13, "symbol": "BTC/USDT", "side": "SELL", "qty": 1.0,
        "requested_qty": 1.0, "broker_id": "binance", "execution_mode": "live",
        "order_status": "pending", "metadata": {"cooldown_bars": 2},
        "filled_qty": 0.0, "is_test": False,
    }
    class Broker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "partially_filled", "filled_qty": 0.5,
                "filled_price": 100.0, "metadata": {"cooldown_bars": 2},
            }

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *args, **kwargs: None)

    updated = trading_api.reconcile_trade_order(trade, {})
    assert updated["_completed_exit_transition"] is False



def test_reconciliation_preserves_submission_metadata(monkeypatch):
    import backend.trading_api as trading_api

    trade = {
        "id": 21, "symbol": "BTC/USDT", "side": "SELL", "qty": 1.0,
        "requested_qty": 1.0, "broker_id": "binance", "execution_mode": "live",
        "order_status": "partially_filled", "broker_order_id": "sell-21",
        "metadata": {"cooldown_bars": 3, "interval": "1h"}, "filled_qty": 0.4,
        "filled_price": 100.0, "is_test": False,
    }
    class Broker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "filled", "broker_order_id": "sell-21",
                "metadata": {"broker_reason": "FILLED"}, "filled_qty": 1.0,
                "filled_price": 101.0,
            }

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *args, **kwargs: None)

    updated = trading_api.reconcile_trade_order(trade, {})
    assert updated["metadata"]["cooldown_bars"] == 3
    assert updated["metadata"]["interval"] == "1h"
    assert updated["metadata"]["broker_reason"] == "FILLED"


def test_reconciliation_rejects_regressive_cumulative_fill(monkeypatch):
    import backend.trading_api as trading_api

    trade = {
        "id": 22, "symbol": "BTC/USDT", "side": "BUY", "qty": 2.0,
        "requested_qty": 2.0, "broker_id": "binance", "execution_mode": "live",
        "order_status": "partially_filled", "broker_order_id": "buy-22",
        "metadata": {}, "filled_qty": 1.25, "filled_price": 100.0, "is_test": False,
    }
    class Broker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "partially_filled", "broker_order_id": "buy-22",
                "metadata": {}, "filled_qty": 0.5, "filled_price": 100.0,
            }

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    persisted = []
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *args, **kwargs: persisted.append(args))

    with pytest.raises(ValueError, match="cumulative filled quantity regressed"):
        trading_api.reconcile_trade_order(trade, {})
    assert persisted == []


def test_reconciled_sell_without_requested_quantity_does_not_complete_exit(monkeypatch):
    import backend.trading_api as trading_api

    trade = {
        "id": 23, "symbol": "BTC/USDT", "side": "SELL", "qty": 0,
        "broker_id": "binance", "execution_mode": "live",
        "order_status": "partially_filled", "broker_order_id": "sell-23",
        "metadata": {"cooldown_bars": 2}, "filled_qty": 0,
        "filled_price": 0, "is_test": False,
    }
    class Broker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "filled", "broker_order_id": "sell-23",
                "metadata": {}, "filled_qty": 0.5, "filled_price": 100.0,
            }

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *args, **kwargs: None)

    updated = trading_api.reconcile_trade_order(trade, {})
    assert updated["_completed_exit_transition"] is False



@pytest.mark.asyncio
async def test_reconciliation_runs_even_when_strategy_has_no_signal(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.config = {
        "symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1h",
        "broker_id": "paper", "execution_mode": "paper",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-26T12:00:00Z")]),
    )
    calls = {"reconcile": 0, "evaluate": 0}

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {})
    monkeypatch.setattr(trading_api, "get_trades", lambda limit=100: [])

    def reconcile(*args, **kwargs):
        calls["reconcile"] += 1
        return []

    def evaluate(*args, **kwargs):
        calls["evaluate"] += 1
        return frame.assign(signal=0)

    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", reconcile)
    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", evaluate)
    monkeypatch.setattr(trading_api.trading_engine, "get_signal", lambda df: None)

    async def stop_after_first_sleep(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_first_sleep)
    await manager.run_loop()

    assert calls["reconcile"] == 1
    assert calls["evaluate"] == 1
    assert any("No signal detected." in entry for entry in manager.logs)



@pytest.mark.parametrize(
    ("stop", "take", "expected"),
    [
        (0, 0, {"stop_loss_pct": 0.0, "take_profit_pct": 0.0}),
        (2.5, 4, {"stop_loss_pct": 2.5, "take_profit_pct": 4.0}),
        ("3", "5.5", {"stop_loss_pct": 3.0, "take_profit_pct": 5.5}),
    ],
)
def test_resolve_position_protection_params_accepts_bounded_percentages(stop, take, expected):
    import pandas as pd
    from backend.trading_api import resolve_position_protection_params

    frame = pd.DataFrame({"stop_loss_pct": [stop], "take_profit_pct": [take]})
    assert resolve_position_protection_params(frame) == expected


def test_resolve_position_protection_params_defaults_missing_columns_to_zero():
    import pandas as pd
    from backend.trading_api import resolve_position_protection_params

    assert resolve_position_protection_params(pd.DataFrame({"signal": [1]})) == {
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
    }


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("stop_loss_pct", -1),
        ("stop_loss_pct", 101),
        ("stop_loss_pct", True),
        ("take_profit_pct", -1),
        ("take_profit_pct", 101),
        ("take_profit_pct", True),
        ("take_profit_pct", "bad"),
    ],
)
def test_resolve_position_protection_params_rejects_invalid_values(column, value):
    import pandas as pd
    from backend.trading_api import resolve_position_protection_params

    values = {"stop_loss_pct": 2.0, "take_profit_pct": 3.0}
    values[column] = value
    frame = pd.DataFrame({key: pd.Series([item], dtype="object") for key, item in values.items()})
    with pytest.raises(ValueError, match=column):
        resolve_position_protection_params(frame)



@pytest.mark.asyncio
async def test_confirmed_long_blocks_runtime_buy_before_order_submission(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api
    from core.position_ledger import ConfirmedPosition

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.config = {
        "symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1h",
        "broker_id": "paper", "execution_mode": "paper",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-26T12:00:00Z")]),
    )

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {})
    monkeypatch.setattr(trading_api, "get_trades", lambda limit=100: [])
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", lambda *args: frame.assign(signal=1))
    monkeypatch.setattr(trading_api.trading_engine, "get_signal", lambda df: "BUY")
    monkeypatch.setattr(
        trading_api,
        "reconstruct_confirmed_position",
        lambda *args, **kwargs: ConfirmedPosition(
            symbol="BTC/USDT", broker_id="paper", execution_mode="paper",
            qty=1.0, average_entry_price=100.0, cost_basis=100.0,
            stop_loss_pct=2.0, take_profit_pct=4.0,
        ),
    )
    monkeypatch.setattr(
        trading_api, "get_risk_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("risk context must not be reached")),
    )
    monkeypatch.setattr(
        trading_api, "submit_guarded_order",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("order submission must not be reached")),
    )

    async def stop_after_sleep(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_sleep)
    await manager.run_loop()

    assert any("BUY BLOCKED: confirmed long position already open" in entry for entry in manager.logs)



@pytest.mark.asyncio
async def test_runtime_submits_guarded_stop_loss_exit_before_strategy_evaluation(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api
    from backend.broker_integration.base import BrokerExecutionResult
    from core.position_ledger import ConfirmedPosition

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.config = {
        "symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1h",
        "broker_id": "paper", "execution_mode": "paper",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [98.0], "high": [98.5], "low": [97.0], "close": [97.5], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-26T13:00:00Z")]),
    )

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api.market_data, "get_latest_price", lambda *args, **kwargs: 96.8)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {})
    monkeypatch.setattr(trading_api, "get_trades", lambda limit=100: [])
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(trading_api, "has_unresolved_order", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        trading_api, "reconstruct_confirmed_position",
        lambda *args, **kwargs: ConfirmedPosition(
            symbol="BTC/USDT", broker_id="paper", execution_mode="paper",
            qty=1.25, average_entry_price=100.0, cost_basis=125.0,
            stop_loss_pct=2.0, take_profit_pct=4.0,
        ),
    )
    monkeypatch.setattr(trading_api, "get_risk_context", lambda *args: (1000.0, 1.25, 1000.0, 1000.0))
    monkeypatch.setattr(
        trading_api.trading_engine, "evaluate_strategy",
        lambda *args: (_ for _ in ()).throw(AssertionError("strategy must not run after protective submission")),
    )

    submitted = []
    def fake_submit_guarded_order(**kwargs):
        submitted.append(kwargs["order"])
        return BrokerExecutionResult(
            broker_id="paper", execution_mode="paper", status="filled",
            message="protective sell filled", filled_qty=1.25, filled_price=97.5,
            metadata={"broker_order_id": "protect-1"},
        )

    monkeypatch.setattr(trading_api, "submit_guarded_order", fake_submit_guarded_order)

    async def stop_after_sleep(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_sleep)
    await manager.run_loop()

    assert len(submitted) == 1
    order = submitted[0]
    assert order.side == "SELL"
    assert order.qty == pytest.approx(1.25)
    assert order.price == pytest.approx(96.8)
    assert order.metadata["protection_reason"] == "stop_loss"
    assert order.metadata["protection_trigger_price"] == pytest.approx(98.0)
    assert order.metadata["protection_observation_price"] == pytest.approx(97.5)
    assert order.metadata["execution_reference_price"] == pytest.approx(96.8)
    assert any("PROTECTION TRIGGERED: stop_loss" in entry for entry in manager.logs)



@pytest.mark.asyncio
async def test_runtime_protection_does_not_race_unresolved_order(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api
    from core.position_ledger import ConfirmedPosition

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.config = {
        "symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1h",
        "broker_id": "paper", "execution_mode": "paper",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [98.0], "high": [98.5], "low": [97.0], "close": [97.5], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-26T14:00:00Z")]),
    )
    unresolved = [{
        "id": 7, "symbol": "BTC/USDT", "side": "BUY", "broker_id": "paper",
        "execution_mode": "paper", "order_status": "partially_filled",
        "requested_qty": 2.0, "filled_qty": 1.0, "filled_price": 100.0,
        "is_test": False, "metadata": {"stop_loss_pct": 2.0, "take_profit_pct": 4.0},
    }]

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {})
    monkeypatch.setattr(trading_api, "get_trades", lambda limit=100: unresolved)
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda *args, **kwargs: unresolved)
    monkeypatch.setattr(trading_api, "has_unresolved_order", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        trading_api, "reconstruct_confirmed_position",
        lambda *args, **kwargs: ConfirmedPosition(
            symbol="BTC/USDT", broker_id="paper", execution_mode="paper",
            qty=1.0, average_entry_price=100.0, cost_basis=100.0,
            stop_loss_pct=2.0, take_profit_pct=4.0,
        ),
    )
    monkeypatch.setattr(
        trading_api, "get_risk_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("risk context must not be reached while an order is unresolved")
        ),
    )
    monkeypatch.setattr(
        trading_api, "submit_guarded_order",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("protective order must not race an unresolved order")
        ),
    )
    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", lambda *args: frame.assign(signal=0))
    monkeypatch.setattr(trading_api.trading_engine, "get_signal", lambda df: None)

    async def stop_after_sleep(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_sleep)
    await manager.run_loop()

    assert any("PROTECTION TRIGGERED: stop_loss" in entry for entry in manager.logs)
    assert any("PROTECTION ORDER BLOCKED: unresolved prior broker order" in entry for entry in manager.logs)



@pytest.mark.asyncio
async def test_runtime_protection_fails_closed_on_position_drift(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api
    from core.position_ledger import ConfirmedPosition

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.config = {
        "symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1h",
        "broker_id": "paper", "execution_mode": "paper",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [98.0], "high": [98.5], "low": [97.0], "close": [97.5], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-26T13:00:00Z")]),
    )

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api.market_data, "get_completed_candles", lambda df, interval: df)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {})
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args: [])
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(trading_api, "has_unresolved_order", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        trading_api, "reconstruct_confirmed_position",
        lambda *args, **kwargs: ConfirmedPosition(
            symbol="BTC/USDT", broker_id="paper", execution_mode="paper",
            qty=1.0, average_entry_price=100.0, cost_basis=100.0,
            stop_loss_pct=2.0, take_profit_pct=4.0,
        ),
    )
    monkeypatch.setattr(
        trading_api, "get_risk_context",
        lambda *args: (1000.0, 0.7, 1000.0, 1000.0),
    )
    monkeypatch.setattr(
        trading_api, "submit_guarded_order",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("position drift must block protective submission")
        ),
    )
    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", lambda *args: frame.assign(signal=0))
    monkeypatch.setattr(trading_api.trading_engine, "get_signal", lambda df: None)

    async def stop_after_sleep(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_sleep)
    await manager.run_loop()

    assert any("PROTECTION TRIGGERED: stop_loss" in entry for entry in manager.logs)
    assert any("PROTECTION ORDER BLOCKED: POSITION DRIFT" in entry for entry in manager.logs)


@pytest.mark.asyncio
async def test_armed_kill_switch_reconciles_but_skips_strategy_evaluation(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.config = {
        "symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1h",
        "broker_id": "paper", "execution_mode": "paper",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-26T12:00:00Z")]),
    )
    calls = {"reconcile": 0, "evaluate": 0}

    class DummyBroker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": True})
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args, **kwargs: [])

    def reconcile(*args, **kwargs):
        calls["reconcile"] += 1
        return []

    def evaluate(*args, **kwargs):
        calls["evaluate"] += 1
        return frame.assign(signal=0)

    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", reconcile)
    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", evaluate)

    async def stop_after_poll(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_poll)
    await manager.run_loop()

    assert calls["reconcile"] == 1
    assert calls["evaluate"] == 0
    assert any("AUTONOMY PAUSED" in entry for entry in manager.logs)
