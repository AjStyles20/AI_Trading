from core.risk_engine import RiskEngine
import pytest


def test_paper_order_within_limit_is_approved():
    decision = RiskEngine().evaluate_order(
        side="BUY",
        qty=1,
        price=100,
        execution_mode="paper",
        settings={"risk_max_order_notional": 1000},
    )
    assert decision.approved is True


def test_order_over_notional_limit_is_rejected():
    decision = RiskEngine().evaluate_order(
        side="BUY",
        qty=2,
        price=600,
        execution_mode="paper",
        settings={"risk_max_order_notional": 1000},
    )
    assert decision.approved is False
    assert "exceeds configured limit" in " ".join(decision.reasons)


def test_live_trading_is_locked_by_default():
    decision = RiskEngine().evaluate_order(
        side="BUY",
        qty=1,
        price=100,
        execution_mode="live",
        settings={"risk_max_order_notional": 1000},
    )
    assert decision.approved is False
    assert "Live trading is locked" in " ".join(decision.reasons)


def test_live_trading_requires_explicit_opt_in():
    decision = RiskEngine().evaluate_order(
        side="BUY",
        qty=1,
        price=100,
        execution_mode="live",
        settings={
            "risk_max_order_notional": 1000,
            "risk_live_trading_enabled": True,
        },
    )
    assert decision.approved is True


def test_invalid_quantity_and_price_are_rejected():
    decision = RiskEngine().evaluate_order(
        side="BUY",
        qty=0,
        price=0,
        execution_mode="paper",
        settings={},
    )
    assert decision.approved is False
    assert len(decision.reasons) >= 2


def test_rejects_sell_larger_than_current_position():
    decision = RiskEngine().evaluate_order(
        side="SELL", qty=2, price=100, execution_mode="paper",
        settings={"risk_max_order_notional": 1000},
        current_position_qty=1,
    )
    assert not decision.approved
    assert "exceeds current position" in decision.reasons[0]


def test_rejects_buy_above_position_equity_limit():
    decision = RiskEngine().evaluate_order(
        side="BUY", qty=3, price=100, execution_mode="paper",
        settings={"risk_max_order_notional": 1000, "risk_max_position_pct": 25},
        account_equity=1000,
    )
    assert not decision.approved
    assert "per-position equity limit" in decision.reasons[0]


def test_daily_loss_limit_blocks_new_orders():
    decision = RiskEngine().evaluate_order(
        side="BUY", qty=1, price=100, execution_mode="paper",
        settings={"risk_max_order_notional": 1000, "risk_max_daily_loss_pct": 3},
        account_equity=960,
        day_start_equity=1000,
        peak_equity=1000,
    )
    assert not decision.approved
    assert "Daily loss" in " ".join(decision.reasons)


def test_drawdown_limit_blocks_new_orders():
    decision = RiskEngine().evaluate_order(
        side="BUY", qty=1, price=100, execution_mode="paper",
        settings={"risk_max_order_notional": 1000, "risk_max_drawdown_pct": 10},
        account_equity=890,
        day_start_equity=900,
        peak_equity=1000,
    )
    assert not decision.approved
    assert "Account drawdown" in " ".join(decision.reasons)


def test_loss_limits_allow_order_below_thresholds():
    decision = RiskEngine().evaluate_order(
        side="BUY", qty=1, price=100, execution_mode="paper",
        settings={
            "risk_max_order_notional": 1000,
            "risk_max_daily_loss_pct": 3,
            "risk_max_drawdown_pct": 10,
        },
        account_equity=980,
        day_start_equity=1000,
        peak_equity=1000,
    )
    assert decision.approved


@pytest.mark.parametrize("field", ["qty", "price"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_order_inputs_cannot_bypass_risk(field, value):
    inputs = dict(side="BUY", qty=1.0, price=100.0, execution_mode="paper")
    inputs[field] = value
    decision = RiskEngine().evaluate_order(**inputs)
    assert not decision.approved
    assert "finite" in " ".join(decision.reasons)


@pytest.mark.parametrize("setting", ["risk_max_order_notional", "risk_max_position_pct", "risk_max_daily_loss_pct", "risk_max_drawdown_pct"])
def test_nonfinite_risk_limits_fail_closed(setting):
    decision = RiskEngine().evaluate_order(
        side="BUY", qty=1.0, price=100.0, execution_mode="paper",
        settings={setting: float("nan")}, account_equity=1000.0,
    )
    assert not decision.approved


def test_nonfinite_equity_and_position_fail_closed():
    decision = RiskEngine().evaluate_order(
        side="SELL", qty=1.0, price=100.0, execution_mode="paper",
        account_equity=float("nan"), current_position_qty=float("nan"),
        day_start_equity=float("nan"), peak_equity=float("nan"),
    )
    assert not decision.approved


def test_notional_overflow_fails_closed():
    decision = RiskEngine().evaluate_order(
        side="BUY", qty=1e200, price=1e200, execution_mode="paper",
    )
    assert not decision.approved
