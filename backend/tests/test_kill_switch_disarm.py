import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import trading_api  # noqa: E402  (the module the app's routes use)
from database import sqlite_manager  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1:8000")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "disarm.db"))
    sqlite_manager.init_db()
    monkeypatch.setattr(trading_api.trading_manager, "is_running", False)


def armed():
    return sqlite_manager.get_settings()["autonomy_kill_switch"]


def disarm(confirmation="DISARM"):
    return client.post("/api/trading/kill-switch/disarm", json={"confirmation": confirmation})


def test_new_install_is_armed():
    assert armed() is True


@pytest.mark.parametrize("typed", ["", "disarm", "DISARM ", "yes"])
def test_disarm_needs_the_exact_confirmation(typed):
    response = disarm(typed)
    assert response.status_code == 400
    assert armed() is True


def test_disarm_works_for_paper_and_is_audited():
    response = disarm()
    assert response.status_code == 200
    assert armed() is False

    event = sqlite_manager.get_audit_events(1)[0]
    assert event["details"]["changes"] == {"autonomy_kill_switch": {"from": True, "to": False}}
    assert "paper only" in event["details"]["source"]


def test_disarm_is_refused_while_live_trading_is_enabled():
    sqlite_manager.update_settings(risk_live_trading_enabled=True)

    response = disarm()
    assert response.status_code == 400
    assert "only disarms for paper" in response.json()["detail"]
    assert armed() is True


def test_disarm_is_refused_while_a_live_session_runs(monkeypatch):
    monkeypatch.setattr(trading_api.trading_manager, "is_running", True)
    monkeypatch.setattr(trading_api.trading_manager, "config", {**trading_api.trading_manager.config, "execution_mode": "live"})

    assert disarm().status_code == 400
    assert armed() is True


def test_live_trading_cannot_be_enabled_while_disarmed():
    assert disarm().status_code == 200

    response = client.post("/api/settings", json={"risk_live_trading_enabled": True})
    assert response.status_code == 400
    assert "Arm the kill switch" in response.json()["detail"]
    assert sqlite_manager.get_settings()["risk_live_trading_enabled"] is False


def test_live_trading_can_be_enabled_together_with_arming():
    assert disarm().status_code == 200

    response = client.post("/api/settings", json={"risk_live_trading_enabled": True, "autonomy_kill_switch": True})
    assert response.status_code == 200
    assert armed() is True
    assert sqlite_manager.get_settings()["risk_live_trading_enabled"] is True


def test_arming_still_works_in_one_step():
    assert disarm().status_code == 200
    assert client.post("/api/settings", json={"autonomy_kill_switch": True}).status_code == 200
    assert armed() is True
