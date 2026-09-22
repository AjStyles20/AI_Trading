from fastapi.testclient import TestClient
import pytest
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_get_settings():
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "theme" in data

def test_market_history_crypto():
    payload = {
        "symbol": "BTC/USDT",
        "asset_type": "crypto",
        "interval": "1d",
        "period": "1y",
        "limit": 500
    }
    response = client.post("/api/market/history", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "timestamp" in data[0]

def test_market_history_stock():
    payload = {
        "symbol": "AAPL",
        "asset_type": "stock",
        "interval": "1d",
        "period": "10d"
    }
    response = client.post("/api/market/history", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)

def test_backtest_execution():
    strategy_code = """
def strategy(data):
    df = data.copy()
    df['signal'] = 0
    if len(df) > 5:
        df.iloc[-1, df.columns.get_loc('signal')] = 1
    return df
"""
    payload = {
        "symbol": "BTC/USDT",
        "asset_type": "crypto",
        "interval": "1d",
        "period": "1d",
        "initial_balance": 10000,
        "fee_pct": 0.1,
        "slippage_pct": 0.05,
        "strategy_code": strategy_code
    }
    response = client.post("/api/backtest/run", json=payload)
    # The backtest might fail with 400 if yfinance has no data, which is acceptable handled behavior, 
    # but we just want to ensure it doesn't 500 crash.
    assert response.status_code in [200, 400]
