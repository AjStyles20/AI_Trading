import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import sqlite_manager  # noqa: E402
import alerts_api  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "alerts.db"))
    sqlite_manager.init_db()


def add(**overrides):
    body = {"symbol": "btc/usdt", "asset_type": "crypto", "direction": "above", "price": 90000, **overrides}
    return client.post("/api/alerts", json=body)


def test_alerts_are_created_listed_and_deleted():
    created = add(note="  breakout  ").json()
    assert created["symbol"] == "BTC/USDT"
    assert created["note"] == "breakout"
    assert created["triggered_at"] is None

    assert [a["id"] for a in client.get("/api/alerts").json()["items"]] == [created["id"]]
    assert client.delete(f"/api/alerts/{created['id']}").status_code == 200
    assert client.get("/api/alerts").json()["items"] == []
    assert client.delete(f"/api/alerts/{created['id']}").status_code == 404


@pytest.mark.parametrize("bad", [
    {"price": 0}, {"price": -1}, {"direction": "sideways"}, {"asset_type": "forex"},
    {"symbol": "BTC\nUSDT"}, {"note": "x" * 201},
])
def test_invalid_alerts_are_rejected(bad):
    assert add(**bad).status_code == 422


def test_trigger_is_confirmed_against_the_level_and_recorded_once():
    above = add(direction="above", price=100).json()
    below = add(direction="below", price=50, symbol="AAPL", asset_type="stock").json()

    assert client.post(f"/api/alerts/{above['id']}/trigger", json={"price": 99.9}).status_code == 400
    assert client.post(f"/api/alerts/{below['id']}/trigger", json={"price": 50.1}).status_code == 400

    first = client.post(f"/api/alerts/{above['id']}/trigger", json={"price": 101}).json()
    assert first["triggered_price"] == 101 and first["triggered_at"]
    again = client.post(f"/api/alerts/{above['id']}/trigger", json={"price": 150}).json()
    assert again["triggered_price"] == 101

    assert client.post(f"/api/alerts/{below['id']}/trigger", json={"price": 49}).json()["triggered_price"] == 49
    assert client.post("/api/alerts/9999/trigger", json={"price": 1}).status_code == 404


def test_active_alerts_are_listed_before_triggered_ones():
    first = add(price=100).json()
    second = add(price=200).json()
    client.post(f"/api/alerts/{first['id']}/trigger", json={"price": 100})

    assert [a["id"] for a in client.get("/api/alerts").json()["items"]] == [second["id"], first["id"]]


def test_active_alert_count_is_limited(monkeypatch):
    monkeypatch.setattr(alerts_api, "MAX_ACTIVE_ALERTS", 2)
    assert add().status_code == 200
    assert add().status_code == 200
    response = add()
    assert response.status_code == 400
    assert "up to 2 active alerts" in response.json()["detail"]
