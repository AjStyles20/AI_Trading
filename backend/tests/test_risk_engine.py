from core.risk_engine import RiskEngine


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
