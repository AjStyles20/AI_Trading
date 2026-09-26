import pandas as pd
from fastapi.testclient import TestClient

from backend.main import app
import sys

backtest_api = sys.modules.get("backtest_api") or sys.modules["backend.backtest_api"]


client = TestClient(app)


def market_frame():
    return pd.DataFrame({
        "open": [100, 101, 102, 103, 104, 105],
        "high": [101, 102, 103, 104, 105, 106],
        "low": [99, 100, 101, 102, 103, 104],
        "close": [100, 101, 102, 103, 104, 105],
    })


def base_payload():
    return {
        "symbol": "TEST",
        "asset_type": "stock",
        "interval": "1d",
        "period": "1y",
        "initial_balance": 10000,
        "fee_pct": 0.1,
        "slippage_pct": 0.05,
    }


def test_backtest_accepts_inline_declarative_strategy(monkeypatch):
    monkeypatch.setattr(backtest_api.market_data, "get_stock_data", lambda *args: market_frame())
    payload = base_payload()
    payload["strategy_spec"] = {
        "schema_version": 1,
        "strategy_type": "sma_cross",
        "params": {
            "sma_fast": 2, "sma_slow": 3,
            "position_size_pct": 50,
            "stop_loss_pct": 2, "take_profit_pct": 4,
        },
    }
    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["scenario"]["strategy_format"] == "declarative_v1"


def test_backtest_accepts_saved_declarative_strategy(monkeypatch):
    monkeypatch.setattr(backtest_api.market_data, "get_stock_data", lambda *args: market_frame())
    monkeypatch.setattr(backtest_api, "get_strategy", lambda strategy_id: {
        "id": strategy_id,
        "strategy_format": "declarative_v1",
        "code": "",
        "strategy_spec": {
            "schema_version": 1,
            "strategy_type": "sma_cross",
            "params": {
                "sma_fast": 2, "sma_slow": 3,
                "position_size_pct": 50,
                "stop_loss_pct": 2, "take_profit_pct": 4,
            },
        },
    })
    payload = base_payload()
    payload["strategy_id"] = 42
    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 200, response.text
    scenario = response.json()["scenario"]
    assert scenario["strategy_format"] == "declarative_v1"
    assert scenario["strategy_id"] == 42


def test_backtest_rejects_ambiguous_strategy_sources(monkeypatch):
    monkeypatch.setattr(backtest_api.market_data, "get_stock_data", lambda *args: market_frame())
    payload = base_payload()
    payload["strategy_code"] = "def strategy(df):\n    return df"
    payload["strategy_spec"] = {
        "schema_version": 1,
        "strategy_type": "sma_cross",
        "params": {"sma_fast": 2, "sma_slow": 3},
    }
    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 400
    assert "exactly one strategy source" in response.json()["detail"]


def test_backtest_rejects_missing_saved_strategy(monkeypatch):
    monkeypatch.setattr(backtest_api.market_data, "get_stock_data", lambda *args: market_frame())
    monkeypatch.setattr(backtest_api, "get_strategy", lambda strategy_id: None)
    payload = base_payload()
    payload["strategy_id"] = 999
    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 400
    assert "Saved strategy not found" in response.json()["detail"]
