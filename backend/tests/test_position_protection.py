import pytest

from core.position_ledger import ConfirmedPosition
from core.position_protection import evaluate_position_protection


def position(qty=2.0, entry=100.0):
    return ConfirmedPosition(
        symbol="BTC/USDT",
        broker_id="binance",
        execution_mode="live",
        qty=qty,
        average_entry_price=entry,
        cost_basis=qty * entry,
    )


@pytest.mark.parametrize(
    ("market_price", "expected_exit", "reason"),
    [
        (98.01, False, None),
        (98.0, True, "stop_loss"),
        (97.0, True, "stop_loss"),
        (102.99, False, None),
        (103.0, True, "take_profit"),
        (104.0, True, "take_profit"),
    ],
)
def test_position_protection_matches_backtest_threshold_boundaries(market_price, expected_exit, reason):
    decision = evaluate_position_protection(
        position(), market_price=market_price, stop_loss_pct=2.0, take_profit_pct=3.0
    )
    assert decision.should_exit is expected_exit
    assert decision.reason == reason


def test_position_protection_returns_exact_trigger_price():
    stop = evaluate_position_protection(position(entry=250.0), market_price=237.5, stop_loss_pct=5.0)
    take = evaluate_position_protection(position(entry=250.0), market_price=275.0, take_profit_pct=10.0)
    assert stop.trigger_price == pytest.approx(237.5)
    assert take.trigger_price == pytest.approx(275.0)


def test_position_protection_disabled_thresholds_do_not_exit():
    decision = evaluate_position_protection(position(), market_price=1.0)
    assert decision.should_exit is False
    assert decision.reason is None


def test_position_protection_flat_position_does_not_exit():
    decision = evaluate_position_protection(position(qty=0.0, entry=0.0), market_price=100.0, stop_loss_pct=2.0)
    assert decision.should_exit is False
    assert decision.position_qty == 0.0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"market_price": 0.0}, "market_price"),
        ({"market_price": 100.0, "stop_loss_pct": -1.0}, "stop_loss_pct"),
        ({"market_price": 100.0, "stop_loss_pct": 101.0}, "stop_loss_pct"),
        ({"market_price": 100.0, "take_profit_pct": -1.0}, "take_profit_pct"),
        ({"market_price": 100.0, "take_profit_pct": 101.0}, "take_profit_pct"),
    ],
)
def test_position_protection_rejects_invalid_inputs(kwargs, message):
    with pytest.raises(ValueError, match=message):
        evaluate_position_protection(position(), **kwargs)


def test_position_protection_rejects_open_position_without_entry_basis():
    with pytest.raises(ValueError, match="average_entry_price"):
        evaluate_position_protection(position(qty=1.0, entry=0.0), market_price=100.0, stop_loss_pct=2.0)
