from fastapi.testclient import TestClient

import backend.trading_api as trading_api
from backend.main import app


client = TestClient(app)


def test_test_order_risk_rejection_never_reaches_broker(monkeypatch):
    calls = {"test_order": 0}

    class DummyBroker:
        broker_id = "paper"
        display_name = "Paper"
        supported_asset_types = {"crypto"}

        def get_account_summary(self, settings, execution_mode):
            return {
                "equity": 1000.0,
                "cash": 1000.0,
                "positions": [],
            }

        def test_order(self, order, execution_mode, settings):
            calls["test_order"] += 1
            raise AssertionError("broker.test_order must not run after a risk rejection")

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: DummyBroker())
    monkeypatch.setattr(trading_api, "resolve_market_price", lambda symbol, asset_type: 100.0)
    monkeypatch.setattr(
        trading_api,
        "get_settings",
        lambda: {
            "risk_max_order_notional": 100.0,
            "risk_max_position_pct": 100.0,
            "risk_max_daily_loss_pct": 3.0,
            "risk_max_drawdown_pct": 10.0,
            "risk_live_trading_enabled": False,
        },
    )
    monkeypatch.setattr(
        trading_api,
        "get_risk_context",
        lambda *args, **kwargs: (1000.0, 0.0, 1000.0, 1000.0),
    )

    response = client.post(
        "/api/trading/test-order",
        json={
            "symbol": "BTC/USDT",
            "asset_type": "crypto",
            "broker_id": "paper",
            "execution_mode": "paper",
            "side": "BUY",
            "qty": 2.0,
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["message"] == "Risk engine blocked test order."
    assert body["detail"]["risk"]["approved"] is False
    assert calls["test_order"] == 0
