from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

import backend.trading_api as trading_api
from backend.broker_integration.base import BrokerExecutionResult, BrokerOrder
from database import sqlite_manager


def _order():
    return BrokerOrder("BTC/USDT", "BUY", 1.0, 100.0, "crypto", {})


def _submit(broker):
    return trading_api.submit_guarded_order(
        broker=broker, order=_order(), settings={}, execution_mode="paper",
        broker_id="paper", account_equity=1000.0, current_position_qty=0.0,
        day_start_equity=1000.0, peak_equity=1000.0,
    )


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "orders.db"))
    sqlite_manager.init_db()
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": False})


def test_timeout_after_possible_acceptance_survives_restart_and_blocks_duplicate(isolated_store):
    calls = []

    def timeout(order, mode, settings):
        calls.append(order.metadata["client_order_id"])
        raise TimeoutError("response lost")

    broker = SimpleNamespace(validate_order=lambda *a: {"ok": True, "normalized_qty": 1.0}, execute_order=timeout)
    with pytest.raises(ValueError, match="SUBMISSION OUTCOME UNKNOWN"):
        _submit(broker)
    trades = sqlite_manager.get_trades_for_scope("BTC/USDT", "paper", "paper")
    assert len(trades) == 1
    assert trades[0]["order_status"] == "submission_pending"
    assert trades[0]["filled_qty"] == 0
    assert trades[0]["metadata"]["client_order_id"] == calls[0]
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "paper", "paper")

    with pytest.raises(ValueError, match="Unresolved order"):
        _submit(broker)
    assert len(calls) == 1


def test_success_updates_same_intent_without_duplicate_row(isolated_store):
    broker = SimpleNamespace(
        validate_order=lambda *a: {"ok": True, "normalized_qty": 1.0},
        execute_order=lambda order, mode, settings: BrokerExecutionResult(
            "paper", "paper", "filled", "done", 1.0, 101.0,
            {"broker_order_id": "b-1"},
        ),
    )
    _submit(broker)
    trades = sqlite_manager.get_trades_for_scope("BTC/USDT", "paper", "paper")
    assert len(trades) == 1
    assert trades[0]["order_status"] == "filled"
    assert trades[0]["filled_qty"] == 1.0
    assert trades[0]["broker_order_id"] == "b-1"
    assert trades[0]["metadata"]["client_order_id"].startswith("astral-")


def test_invalid_broker_result_keeps_intent_unresolved(isolated_store):
    broker = SimpleNamespace(
        validate_order=lambda *a: {"ok": True, "normalized_qty": 1.0},
        execute_order=lambda order, mode, settings: BrokerExecutionResult(
            "paper", "paper", "filled", "bad", float("nan"), 101.0, {},
        ),
    )
    with pytest.raises(ValueError, match="SUBMISSION OUTCOME UNKNOWN"):
        _submit(broker)
    trades = sqlite_manager.get_trades_for_scope("BTC/USDT", "paper", "paper")
    assert trades[0]["order_status"] == "submission_pending"


def test_reconcile_client_id_after_lost_response(isolated_store, monkeypatch):
    broker = SimpleNamespace(
        get_order_status=lambda trade, settings: {
            "order_status": "filled", "broker_order_id": "recovered-1",
            "filled_qty": 1.0, "filled_price": 101.0, "metadata": {},
        },
    )
    sqlite_manager.record_trade(
        "BTC/USDT", "BUY", 1.0, 100.0, broker_id="binance",
        execution_mode="live", order_status="submission_pending",
        requested_qty=1.0, filled_qty=0.0, filled_price=0.0,
        metadata={"client_order_id": "astral-recovery"},
    )
    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: broker)
    # The actual adapter lookup is covered separately; this checks the durable
    # intent transitions exactly once through the shared reconciler.
    trade = sqlite_manager.get_trades_for_scope("BTC/USDT", "binance", "live")[0]
    result = trading_api.reconcile_trade_order(trade, {})
    assert result["order_status"] == "filled"
    assert sqlite_manager.get_trades_for_scope("BTC/USDT", "binance", "live")[0]["broker_order_id"] == "recovered-1"


def test_concurrent_same_scope_intent_claims_allow_only_one(isolated_store):
    start = Barrier(2)

    def claim():
        start.wait()
        try:
            return sqlite_manager.record_trade(
                "BTC/USDT", "BUY", 1.0, 100.0,
                broker_id="binance", execution_mode="live",
                order_status="submission_pending", requested_qty=1.0,
                filled_qty=0.0, filled_price=0.0,
                require_clear_scope=True,
            )
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: claim(), range(2)))
    assert len([result for result in outcomes if isinstance(result, int)]) == 1
    assert len([result for result in outcomes if "Unresolved order" in str(result)]) == 1
    assert len(sqlite_manager.get_trades_for_scope("BTC/USDT", "binance", "live")) == 1
