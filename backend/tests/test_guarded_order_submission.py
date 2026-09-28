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
    trading_api.get_settings = lambda: {"autonomy_kill_switch": False}
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
    def save_intent(*args, **kwargs):
        persisted.update(args=args, kwargs=kwargs)
        return 42
    monkeypatch.setattr(trading_api, "record_trade", save_intent)
    monkeypatch.setattr(trading_api, "update_trade_order_state", lambda *args, **kwargs: persisted.update(update_args=args, update_kwargs=kwargs))

    result = call(broker, item)

    assert result is execution
    assert item.qty == pytest.approx(1.5)
    assert persisted["kwargs"]["requested_qty"] == pytest.approx(1.5)
    assert persisted["kwargs"]["order_status"] == "submission_pending"
    assert persisted["kwargs"]["filled_qty"] == 0.0
    assert persisted["kwargs"]["require_clear_scope"] is True
    assert persisted["update_args"][:3] == (42, "filled", "p-1")
    assert persisted["update_kwargs"]["filled_qty"] == pytest.approx(1.5)
    assert persisted["update_kwargs"]["filled_price"] == pytest.approx(101.0)


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


@pytest.mark.parametrize("normalized", [float("nan"), float("inf"), 11.0])
def test_guarded_submission_rejects_invalid_or_risk_exceeding_broker_quantity(monkeypatch, normalized):
    item = order()
    broker = SimpleNamespace(
        validate_order=lambda *args, **kwargs: {"ok": True, "normalized_qty": normalized},
        execute_order=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": False})
    monkeypatch.setattr(trading_api, "record_trade", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not persist")))
    with pytest.raises(ValueError, match="Broker-normalized|RISK BLOCKED BROKER-NORMALIZED"):
        trading_api.submit_guarded_order(
            broker=broker, order=item, settings={"risk_max_order_notional": 1000},
            execution_mode="paper", broker_id="paper", account_equity=1000.0,
            current_position_qty=0.0, day_start_equity=1000.0, peak_equity=1000.0,
        )


def test_quote_rejects_nonfinite_and_invalid_side():
    from backend.broker_integration.base import BrokerQuote

    quote = BrokerQuote("venue", "BTC/USDT", bid=float("nan"), ask=float("inf"),
                        last=float("nan"), timestamp=None, source="test")
    with pytest.raises(ValueError, match="no valid execution reference"):
        quote.execution_reference("BUY")
    with pytest.raises(ValueError, match="Unsupported quote side"):
        quote.execution_reference("HOLD")


def test_guarded_submission_kill_switch_blocks_before_risk_broker_or_persistence(monkeypatch):
    item = order()
    broker = SimpleNamespace(
        validate_order=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not validate")),
        execute_order=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": True})
    monkeypatch.setattr(
        trading_api.risk_engine, "evaluate_order",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not evaluate risk")),
    )
    monkeypatch.setattr(
        trading_api, "record_trade",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not persist")),
    )

    with pytest.raises(ValueError, match="KILL SWITCH"):
        trading_api.submit_guarded_order(
            broker=broker, order=item, settings={}, execution_mode="paper",
            broker_id="paper", account_equity=1000.0, current_position_qty=0.0,
            day_start_equity=1000.0, peak_equity=1000.0,
        )


def test_broker_quote_uses_side_appropriate_execution_reference():
    from backend.broker_integration.base import BrokerQuote

    quote = BrokerQuote(
        broker_id="venue", symbol="BTC/USDT",
        bid=99.5, ask=100.5, last=100.0,
        timestamp="2026-09-27T10:00:00Z", source="venue:test",
    )

    assert quote.execution_reference("BUY") == pytest.approx(100.5)
    assert quote.execution_reference("SELL") == pytest.approx(99.5)


def test_broker_quote_falls_back_to_last_when_side_price_missing():
    from backend.broker_integration.base import BrokerQuote

    quote = BrokerQuote(
        broker_id="venue", symbol="ABC",
        bid=None, ask=None, last=42.0,
        timestamp=None, source="venue:last",
    )

    assert quote.execution_reference("BUY") == pytest.approx(42.0)
    assert quote.execution_reference("SELL") == pytest.approx(42.0)


def test_broker_quote_fails_closed_without_valid_price():
    from backend.broker_integration.base import BrokerQuote

    quote = BrokerQuote(
        broker_id="venue", symbol="ABC",
        bid=0.0, ask=0.0, last=None,
        timestamp=None, source="venue:bad",
    )

    with pytest.raises(ValueError, match="no valid execution reference"):
        quote.execution_reference("BUY")
