from types import SimpleNamespace

import pytest

import backend.trading_api as trading_api
from backend.broker_integration.base import BrokerOrder, BrokerExecutionResult


def order():
    return BrokerOrder(
        symbol="BTC/USDT", side="BUY", qty=2.0, price=100.0,
        asset_type="crypto", metadata={"interval": "1h"},
    )


def call(broker, item):
    return trading_api.submit_guarded_order(
        broker=broker, order=item, settings={}, execution_mode="paper",
        broker_id="paper", account_equity=1000.0, current_position_qty=0.0,
        day_start_equity=1000.0, peak_equity=1000.0,
    )


def test_guarded_submission_risk_rejection_has_no_execution_or_persistence(monkeypatch):
    item = order()
    broker = SimpleNamespace()
    broker.validate_order = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not validate"))
    broker.execute_order = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute"))
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: SimpleNamespace(approved=False, reasons=["limit"]))
    monkeypatch.setattr(trading_api, "record_trade", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not persist")))

    with pytest.raises(ValueError, match="RISK BLOCKED ORDER"):
        call(broker, item)


def test_guarded_submission_broker_rejection_has_no_execution_or_persistence(monkeypatch):
    item = order()
    broker = SimpleNamespace(
        validate_order=lambda *args, **kwargs: {"ok": False, "reason": "invalid qty"},
        execute_order=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: SimpleNamespace(approved=True, reasons=[]))
    monkeypatch.setattr(trading_api, "record_trade", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not persist")))

    with pytest.raises(ValueError, match="BROKER VALIDATION BLOCKED ORDER"):
        call(broker, item)


def test_guarded_submission_persists_normalized_requested_and_confirmed_fill(monkeypatch):
    item = order()
    execution = BrokerExecutionResult(
        broker_id="paper", execution_mode="paper", status="filled", message="filled",
        filled_qty=1.5, filled_price=101.0, metadata={"broker_order_id": "p-1"},
    )
    broker = SimpleNamespace(
        validate_order=lambda *args, **kwargs: {"ok": True, "normalized_qty": 1.5},
        execute_order=lambda submitted, *args: execution,
    )
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: SimpleNamespace(approved=True, reasons=[]))
    persisted = {}
    monkeypatch.setattr(trading_api, "record_trade", lambda *args, **kwargs: persisted.update(args=args, kwargs=kwargs))

    result = call(broker, item)

    assert result is execution
    assert item.qty == pytest.approx(1.5)
    assert persisted["kwargs"]["requested_qty"] == pytest.approx(1.5)
    assert persisted["kwargs"]["filled_qty"] == pytest.approx(1.5)
    assert persisted["kwargs"]["filled_price"] == pytest.approx(101.0)
    assert persisted["kwargs"]["broker_order_id"] == "p-1"


def test_guarded_submission_rejects_nonpositive_normalized_quantity(monkeypatch):
    item = order()
    broker = SimpleNamespace(
        validate_order=lambda *args, **kwargs: {"ok": True, "normalized_qty": 0.0},
        execute_order=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: SimpleNamespace(approved=True, reasons=[]))
    monkeypatch.setattr(trading_api, "record_trade", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not persist")))

    with pytest.raises(ValueError, match="greater than zero"):
        call(broker, item)
