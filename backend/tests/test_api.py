from fastapi.testclient import TestClient
import pytest
import sys
import os
import pandas as pd

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
import data_api

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(autouse=True)
def _fresh_history_cache():
    # Chart history is cached between requests; each test supplies its own data.
    data_api.history_cache.clear()
    yield
    data_api.history_cache.clear()

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_get_settings():
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "theme" in data

def _history_frame():
    return pd.DataFrame(
        {"open": [100.0], "high": [102.0], "low": [99.0], "close": [101.0], "volume": [5.0]},
        index=pd.DatetimeIndex(["2026-09-27T00:00:00Z"], name="timestamp"),
    )


def test_market_history_crypto(monkeypatch):
    monkeypatch.setattr(data_api.market_data, "get_crypto_data", lambda *args, **kwargs: _history_frame())
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
        assert data[0]["timestamp"] == 1790467200000

def _long_history_frame(rows):
    return pd.DataFrame(
        {
            "open": [100.0 + i for i in range(rows)],
            "high": [102.0 + i for i in range(rows)],
            "low": [99.0 + i for i in range(rows)],
            "close": [101.0 + i for i in range(rows)],
            "volume": [5.0] * rows,
        },
        index=pd.date_range("2026-09-27", periods=rows, freq="1min", tz="UTC", name="timestamp"),
    )


@pytest.mark.parametrize("asset_type, provider", [("crypto", "get_crypto_data"), ("stock", "get_stock_data")])
def test_market_history_returns_only_the_latest_limit_candles(monkeypatch, asset_type, provider):
    monkeypatch.setattr(data_api.market_data, provider, lambda *args, **kwargs: _long_history_frame(50))
    payload = {"symbol": "BTC/USDT", "asset_type": asset_type, "interval": "1m", "limit": 3}
    response = client.post("/api/market/history", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert [row["close"] for row in data] == [148.0, 149.0, 150.0]


@pytest.mark.parametrize("limit", [0, -1, 5001])
def test_market_history_rejects_out_of_range_limits(limit):
    payload = {"symbol": "BTC/USDT", "asset_type": "crypto", "interval": "1m", "limit": limit}
    response = client.post("/api/market/history", json=payload)
    assert response.status_code == 422


def test_market_history_stock(monkeypatch):
    monkeypatch.setattr(data_api.market_data, "get_stock_data", lambda *args, **kwargs: _history_frame())
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
    assert data[0]["close"] == 101.0

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


def test_crypto_backtest_uses_the_period_the_user_chose(monkeypatch):
    # Crypto research used to ignore the chosen period and always fetch ~600 days,
    # while the report claimed the selected one.
    import backtest_api

    seen = {}

    def fake_crypto(symbol, interval, limit=500, period=None):
        seen["period"] = period
        closes = [100.0 + i for i in range(40)]
        return pd.DataFrame(
            {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1.0] * 40},
            index=pd.date_range("2026-01-01", periods=40, freq="h"),
        )

    monkeypatch.setattr(backtest_api.market_data, "get_crypto_data", fake_crypto)
    response = client.post("/api/backtest/run", json={
        "symbol": "BTC/USDT",
        "asset_type": "crypto",
        "interval": "1h",
        "period": "3mo",
        "strategy_code": "def strategy(df):\n    df['signal'] = 0\n    return df\n",
    })
    assert response.status_code == 200, response.text
    assert seen["period"] == "3mo"
