from core.autonomy_readiness import evaluate_autonomous_readiness


def _status(**overrides):
    value = {
        "configured": True,
        "supports_live": True,
        "supported_asset_types": ["crypto"],
        "capabilities": {
            "market_orders": True,
            "order_status": True,
            "open_orders": True,
            "positions": True,
            "cancellation": True,
        },
    }
    value.update(overrides)
    return value


def test_autonomous_readiness_accepts_consistent_sandbox_state():
    decision = evaluate_autonomous_readiness(
        broker_status=_status(),
        account={"can_trade": True},
        execution_mode="live",
        asset_type="crypto",
        unresolved_order=False,
        ledger_position_qty=1.0,
        broker_position_qty=1.0000005,
        risk_approved=True,
        broker_validation_ok=True,
    )
    assert decision.ready is True
    assert decision.reasons == ()


def test_autonomous_readiness_fails_closed_on_position_drift():
    decision = evaluate_autonomous_readiness(
        broker_status=_status(),
        account={"can_trade": True},
        execution_mode="live",
        asset_type="crypto",
        unresolved_order=False,
        ledger_position_qty=1.0,
        broker_position_qty=0.7,
        risk_approved=True,
        broker_validation_ok=True,
    )
    assert decision.ready is False
    assert any("Position drift" in reason for reason in decision.reasons)


def test_autonomous_readiness_requires_lifecycle_capabilities_and_clean_orders():
    status = _status()
    status["capabilities"] = dict(status["capabilities"], order_status=False)
    decision = evaluate_autonomous_readiness(
        broker_status=status,
        account={"can_trade": True},
        execution_mode="live",
        asset_type="crypto",
        unresolved_order=True,
        ledger_position_qty=0.0,
        broker_position_qty=0.0,
        risk_approved=True,
        broker_validation_ok=True,
    )
    assert decision.ready is False
    assert any("order_status" in reason for reason in decision.reasons)
    assert any("unresolved prior order" in reason for reason in decision.reasons)


def test_missing_cancellation_is_warning_not_false_capability_claim():
    status = _status()
    status["capabilities"] = dict(status["capabilities"], cancellation=False)
    decision = evaluate_autonomous_readiness(
        broker_status=status,
        account={"can_trade": True},
        execution_mode="paper",
        asset_type="crypto",
        unresolved_order=False,
        ledger_position_qty=0.0,
        broker_position_qty=0.0,
        risk_approved=True,
        broker_validation_ok=True,
    )
    assert decision.ready is True
    assert any("cancellation" in warning for warning in decision.warnings)
