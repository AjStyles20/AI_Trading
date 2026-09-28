import backend.trading_api as trading_api
from core.position_ledger import ConfirmedPosition


class DummyRisk:
    def __init__(self, approved=False):
        self.approved = approved

    def as_dict(self):
        return {"approved": self.approved, "reasons": ["reference order too large"] if not self.approved else []}


class DummyBroker:
    broker_id = "dummy"
    display_name = "Dummy"
    supports_live = True
    supported_asset_types = ("crypto",)

    def get_account_summary(self, settings, execution_mode):
        return {"can_trade": True, "configured": True}

    def get_status(self, settings):
        return {
            "broker_id": "dummy",
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
            broker_id="dummy", symbol=symbol,
            bid=price - 1.0, ask=price + 1.0, last=price,
            timestamp="2026-09-28T00:00:00Z", source="dummy:test_quote",
        )

    def validate_order(self, order, execution_mode, settings):
        return {"ok": False, "reason": "diagnostic reference order rejected"}


def test_builder_recovery_uses_reconciled_ledger_and_broker_position(monkeypatch):
    broker = DummyBroker()
    raw = [{"id": 1, "order_status": "submitted"}]
    reconciled = [{"id": 1, "order_status": "filled"}]

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: broker)
    monkeypatch.setattr(trading_api, "resolve_market_price", lambda *args: 100000.0)
    monkeypatch.setattr(
        trading_api, "get_risk_context",
        lambda *args, **kwargs: (1000.0, 2.0, 1000.0, 1000.0),
    )
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args: raw)
    seen = {}

    def reconcile(trades, *args, **kwargs):
        seen["input"] = trades
        return reconciled

    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", reconcile)

    def reconstruct(trades, **kwargs):
        seen["reconstruct_input"] = trades
        return ConfirmedPosition(
            symbol="BTC/USDT",
            broker_id="dummy",
            execution_mode="live",
            qty=2.0,
            average_entry_price=90.0,
            cost_basis=180.0,
            stop_loss_pct=None,
            take_profit_pct=None,
        )

    monkeypatch.setattr(trading_api, "reconstruct_confirmed_position", reconstruct)
    monkeypatch.setattr(trading_api, "has_unresolved_order", lambda *args, **kwargs: False)
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: DummyRisk(False))

    result = trading_api.build_autonomous_readiness(
        "BTC/USDT", "crypto", "dummy", "live", {}
    )

    assert seen["input"] is raw
    assert seen["reconstruct_input"] is reconciled
    assert result["ledger_position_qty"] == 2.0
    assert result["broker_position_qty"] == 2.0
    assert result["readiness"]["ready"] is True
    assert result["reference_order_risk"]["approved"] is False
    assert result["reference_order_validation"]["ok"] is False


def test_builder_recovery_fails_on_position_drift(monkeypatch):
    broker = DummyBroker()
    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: broker)
    monkeypatch.setattr(trading_api, "resolve_market_price", lambda *args: 100.0)
    monkeypatch.setattr(
        trading_api, "get_risk_context",
        lambda *args, **kwargs: (1000.0, 0.5, 1000.0, 1000.0),
    )
    monkeypatch.setattr(trading_api, "get_trades_for_scope", lambda *args: [])
    monkeypatch.setattr(trading_api, "reconcile_unresolved_orders", lambda trades, *args, **kwargs: trades)
    monkeypatch.setattr(
        trading_api,
        "reconstruct_confirmed_position",
        lambda *args, **kwargs: ConfirmedPosition(
            symbol="BTC/USDT", broker_id="dummy", execution_mode="live",
            qty=1.0, average_entry_price=100.0, cost_basis=100.0,
            stop_loss_pct=None, take_profit_pct=None,
        ),
    )
    monkeypatch.setattr(trading_api, "has_unresolved_order", lambda *args, **kwargs: False)
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: DummyRisk(True))

    result = trading_api.build_autonomous_readiness(
        "BTC/USDT", "crypto", "dummy", "live", {}
    )

    assert result["readiness"]["ready"] is False
    assert any("Position drift" in reason for reason in result["readiness"]["reasons"])
