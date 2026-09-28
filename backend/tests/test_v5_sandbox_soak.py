import backend.trading_api as trading_api
import pytest


def _base_sell_trade():
    return {
        "id": 501,
        "symbol": "BTC/USDT",
        "side": "SELL",
        "qty": 1.0,
        "requested_qty": 1.0,
        "broker_id": "sandbox",
        "execution_mode": "live",
        "order_status": "submitted",
        "broker_order_id": "order-501",
        "metadata": {"cooldown_bars": 2, "interval": "1h"},
        "filled_qty": 0.0,
        "filled_price": 0.0,
        "is_test": False,
    }


def test_sandbox_soak_partial_fill_outage_recovery_and_single_terminal_transition(monkeypatch):
    responses = iter([
        {
            "order_status": "partially_filled",
            "broker_order_id": "order-501",
            "metadata": {"broker_reason": "PARTIAL_1"},
            "filled_qty": 0.25,
            "filled_price": 100.0,
        },
        RuntimeError("transient broker status outage"),
        {
            "order_status": "partially_filled",
            "broker_order_id": "order-501",
            "metadata": {"broker_reason": "PARTIAL_2"},
            "filled_qty": 0.75,
            "filled_price": 100.5,
        },
        {
            "order_status": "filled",
            "broker_order_id": "order-501",
            "metadata": {"broker_reason": "FILLED"},
            "filled_qty": 1.0,
            "filled_price": 101.0,
        },
    ])

    class ScriptedBroker:
        def get_order_status(self, trade, settings):
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            return item

    persisted = []

    def persist(trade_id, status, broker_order_id, metadata, filled_qty=None, filled_price=None):
        persisted.append(
            {
                "id": trade_id,
                "status": status,
                "filled_qty": filled_qty,
                "filled_price": filled_price,
                "metadata": dict(metadata or {}),
            }
        )

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: ScriptedBroker())
    monkeypatch.setattr(trading_api, "update_trade_order_state", persist)

    trades = [_base_sell_trade()]
    completed_exit_transitions = 0
    observed_fills = []

    # Poll 1: partial fill.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is True

    # Poll 2: broker outage. State must remain unresolved and retain prior fill truth.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trades[0]["order_status"] == "partially_filled"
    assert trades[0]["filled_qty"] == 0.25
    assert "status_refresh_error" in trades[0]["metadata"]
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is True

    # Poll 3: broker recovers with greater cumulative fill.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trades[0]["filled_qty"] == 0.75
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is True

    # Poll 4: terminal fill; exactly one completed SELL transition.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trades[0]["order_status"] == "filled"
    assert trades[0]["filled_qty"] == 1.0
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is False

    # Poll 5: terminal state must not query broker or emit a second exit transition.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))

    assert observed_fills == sorted(observed_fills)
    assert observed_fills == [0.25, 0.25, 0.75, 1.0]
    assert completed_exit_transitions == 1
    assert [entry["filled_qty"] for entry in persisted] == [0.25, 0.75, 1.0]


def test_sandbox_soak_rejects_regressive_fill_without_persisting(monkeypatch):
    trade = _base_sell_trade()
    trade["order_status"] = "partially_filled"
    trade["filled_qty"] = 0.8
    trade["filled_price"] = 100.0

    class RegressiveBroker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "partially_filled",
                "broker_order_id": "order-501",
                "metadata": {"broker_reason": "STALE"},
                "filled_qty": 0.4,
                "filled_price": 100.0,
            }

    persisted = []
    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: RegressiveBroker())
    monkeypatch.setattr(
        trading_api,
        "update_trade_order_state",
        lambda *args, **kwargs: persisted.append((args, kwargs)),
    )

    try:
        trading_api.reconcile_trade_order(trade, {})
    except ValueError as exc:
        assert "cumulative filled quantity regressed" in str(exc)
    else:
        raise AssertionError("Regressive cumulative fill must fail closed.")

    assert persisted == []


@pytest.mark.parametrize("fill,price", [
    (float("nan"), 100.0),
    (float("inf"), 100.0),
    (-0.1, 100.0),
    (1.1, 100.0),
    (0.5, float("nan")),
    (0.5, 0.0),
    (0.0, 0.0),
])
def test_invalid_broker_fill_remains_unresolved_and_is_not_persisted(monkeypatch, fill, price):
    trade = _base_sell_trade()

    class InvalidBroker:
        def get_order_status(self, trade, settings):
            return {"order_status": "filled", "filled_qty": fill, "filled_price": price}

    persisted = []
    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: InvalidBroker())
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *a, **kw: persisted.append((a, kw)))

    reconciled = trading_api.reconcile_unresolved_orders(
        [trade], {}, "BTC/USDT", "sandbox", "live",
    )
    assert persisted == []
    assert reconciled[0]["order_status"] == "submitted"
    assert trading_api.has_unresolved_order(reconciled, "BTC/USDT", "sandbox", "live")
    assert "status_refresh_error" in reconciled[0]["metadata"]


def test_protection_quote_failure_blocks_strategy_for_that_poll(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api
    from core.position_ledger import ConfirmedPosition

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.recovery_verified = True
    manager.config = {
        "symbol": "BTC/USDT",
        "asset_type": "crypto",
        "interval": "1h",
        "broker_id": "sandbox",
        "execution_mode": "live",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [98.0], "high": [98.5], "low": [97.0], "close": [97.5], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-27T12:00:00Z")]),
    )
    calls = {"strategy": 0, "submit": 0}

    class Broker:
        display_name = "Sandbox"
        supported_asset_types = {"crypto"}

        def get_quote(self, *args, **kwargs):
            raise ValueError("quote unavailable")

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api.market_data, "get_completed_candles", lambda df, interval: df)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": False})
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args: [])
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(trading_api, "has_unresolved_order", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        trading_api,
        "reconstruct_confirmed_position",
        lambda *args, **kwargs: ConfirmedPosition(
            symbol="BTC/USDT", broker_id="sandbox", execution_mode="live",
            qty=1.0, average_entry_price=100.0, cost_basis=100.0,
            stop_loss_pct=2.0, take_profit_pct=4.0,
        ),
    )
    monkeypatch.setattr(
        trading_api,
        "get_risk_context",
        lambda *args, **kwargs: (1000.0, 1.0, 1000.0, 1000.0),
    )

    def evaluate(*args, **kwargs):
        calls["strategy"] += 1
        return frame.assign(signal=-1)

    def submit(**kwargs):
        calls["submit"] += 1
        raise AssertionError("no order should submit when protective quote acquisition fails")

    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", evaluate)
    monkeypatch.setattr(trading_api, "submit_guarded_order", submit)

    async def stop_after_sleep(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_sleep)
    import asyncio
    asyncio.run(manager.run_loop())

    assert calls == {"strategy": 0, "submit": 0}
    assert any("PROTECTION ORDER BLOCKED: quote unavailable" in entry for entry in manager.logs)


def test_restart_recovery_blocks_on_unresolved_partial_fill(monkeypatch):
    import backend.trading_api as trading_api
    from core.position_ledger import ConfirmedPosition

    class Broker:
        broker_id = "sandbox"
        display_name = "Sandbox"
        supports_live = True
        supported_asset_types = ("crypto",)

        def get_account_summary(self, settings, execution_mode):
            return {"can_trade": True, "equity": 1000.0, "positions": [{"symbol": "BTC/USDT", "qty": 0.4}]}

        def get_status(self, settings):
            return {
                "configured": True,
                "supports_live": True,
                "supported_asset_types": ["crypto"],
                "capabilities": {
                    "market_orders": True,
                    "quotes": True,
                    "order_status": True,
                    "open_orders": True,
                    "positions": True,
                    "cancellation": True,
                },
            }

        def get_quote(self, symbol, asset_type, settings, execution_mode, reference_price=None):
            from backend.broker_integration.base import BrokerQuote
            price = float(reference_price or 100.0)
            return BrokerQuote(
                broker_id="sandbox", symbol=symbol,
                bid=price - 0.5, ask=price + 0.5, last=price,
                timestamp="2026-09-28T00:00:00Z", source="sandbox:recovery_quote",
            )

        def validate_order(self, order, execution_mode, settings):
            return {"ok": True, "normalized_qty": order.qty}

    partial = [{
        "id": 77, "symbol": "BTC/USDT", "side": "BUY",
        "broker_id": "sandbox", "execution_mode": "live",
        "order_status": "partially_filled", "requested_qty": 1.0,
        "filled_qty": 0.4, "filled_price": 100.0, "metadata": {},
        "is_test": False,
    }]

    broker = Broker()
    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: broker)
    monkeypatch.setattr(trading_api, "resolve_market_price", lambda *args: 100.0)
    monkeypatch.setattr(trading_api, "get_risk_context", lambda *args, **kwargs: (1000.0, 0.4, 1000.0, 1000.0))
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args: partial)
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda trades, *args, **kwargs: trades)
    monkeypatch.setattr(
        trading_api,
        "reconstruct_confirmed_position",
        lambda *args, **kwargs: ConfirmedPosition(
            symbol="BTC/USDT", broker_id="sandbox", execution_mode="live",
            qty=0.4, average_entry_price=100.0, cost_basis=40.0,
            stop_loss_pct=None, take_profit_pct=None,
        ),
    )
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: type("Risk", (), {"as_dict": lambda self: {"approved": True}})())

    result = trading_api.build_autonomous_readiness(
        "BTC/USDT", "crypto", "sandbox", "live", {}
    )

    assert result["readiness"]["ready"] is False
    assert any("unresolved prior order" in reason for reason in result["readiness"]["reasons"])


def test_mid_session_kill_switch_activation_enters_reconcile_only_mode(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.recovery_verified = True
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
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-27T12:00:00Z")]),
    )
    settings_sequence = iter([
        {"autonomy_kill_switch": False},
        {"autonomy_kill_switch": True},
    ])
    calls = {"reconcile": 0, "strategy": 0, "submit": 0, "sleep": 0}

    class Broker:
        display_name = "Paper"
        supported_asset_types = {"crypto"}

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api.market_data, "get_completed_candles", lambda df, interval: df)
    monkeypatch.setattr(trading_api, "get_settings", lambda: next(settings_sequence))
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args: [])

    def reconcile(*args, **kwargs):
        calls["reconcile"] += 1
        return []

    def evaluate(*args, **kwargs):
        calls["strategy"] += 1
        return frame.assign(signal=0)

    def submit(**kwargs):
        calls["submit"] += 1
        raise AssertionError("no order expected in this incident test")

    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", reconcile)
    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", evaluate)
    monkeypatch.setattr(trading_api.trading_engine, "get_signal", lambda df: None)
    monkeypatch.setattr(trading_api, "submit_guarded_order", submit)

    async def controlled_sleep(seconds):
        calls["sleep"] += 1
        if calls["sleep"] >= 2:
            manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", controlled_sleep)

    import asyncio
    asyncio.run(manager.run_loop())

    assert calls["reconcile"] == 2
    assert calls["strategy"] == 1
    assert calls["submit"] == 0
    assert any("AUTONOMY PAUSED: kill switch is armed" in entry for entry in manager.logs)


def test_normal_strategy_order_uses_broker_quote_not_candle_close(monkeypatch):
    import pandas as pd
    import backend.trading_api as trading_api
    from backend.broker_integration.base import BrokerExecutionResult, BrokerQuote

    manager = trading_api.LiveTradingManager()
    manager.is_running = True
    manager.recovery_verified = True
    manager.config = {
        "symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1h",
        "broker_id": "sandbox", "execution_mode": "live",
        "strategy_code": "def strategy(df): return df",
    }
    frame = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [10.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-09-28T00:00:00Z")]),
    )
    submitted = []

    class Broker:
        display_name = "Sandbox"
        supported_asset_types = {"crypto"}

        def get_quote(self, symbol, asset_type, settings, execution_mode, reference_price=None):
            assert reference_price == 100.0
            return BrokerQuote(
                broker_id="sandbox", symbol=symbol,
                bid=99.5, ask=101.5, last=100.5,
                timestamp="2026-09-28T00:00:01Z", source="sandbox:test_quote",
            )

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: Broker())
    monkeypatch.setattr(trading_api.market_data, "get_crypto_data", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(trading_api.market_data, "assert_fresh", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_api.market_data, "get_completed_candles", lambda df, interval: df)
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": False})
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args: [])
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(trading_api, "has_unresolved_order", lambda *args, **kwargs: False)
    monkeypatch.setattr(trading_api.trading_engine, "evaluate_strategy", lambda *args: frame.assign(signal=1, order_qty=1.0))
    monkeypatch.setattr(trading_api.trading_engine, "get_signal", lambda df: "BUY")
    monkeypatch.setattr(trading_api, "get_risk_context", lambda *args, **kwargs: (1000.0, 0.0, 1000.0, 1000.0))
    monkeypatch.setattr(trading_api, "resolve_strategy_quantity", lambda *args, **kwargs: 1.0)

    def submit(**kwargs):
        submitted.append(kwargs["order"])
        return BrokerExecutionResult(
            broker_id="sandbox", execution_mode="live", status="submitted",
            message="submitted", filled_qty=0.0, filled_price=0.0, metadata={},
        )

    monkeypatch.setattr(trading_api, "submit_guarded_order", submit)

    async def stop_after_sleep(seconds):
        manager.is_running = False

    monkeypatch.setattr(trading_api.asyncio, "sleep", stop_after_sleep)
    import asyncio
    asyncio.run(manager.run_loop())

    assert len(submitted) == 1
    order = submitted[0]
    assert order.price == 101.5
    assert order.metadata["signal_observation_price"] == 100.0
    assert order.metadata["execution_quote_source"] == "sandbox:test_quote"
