import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import sqlite_manager  # noqa: E402
import settings_api  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")

FAKE_SECRET = "test-only-not-a-real-credential-1234"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / "audit.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(path))
    sqlite_manager.init_db()
    # Tests must never touch the real OS credential store.
    monkeypatch.setattr(settings_api, "set_secure_credential", lambda key, value: None)
    return path


def events():
    return client.get("/api/audit").json()["items"]


def test_settings_changes_are_recorded_with_old_and_new_values():
    before = sqlite_manager.get_settings()["risk_max_order_notional"]
    assert client.post("/api/settings", json={"risk_max_order_notional": before + 50}).status_code == 200

    latest = events()[0]
    assert (latest["category"], latest["action"]) == ("settings", "updated")
    assert latest["details"]["changes"] == {"risk_max_order_notional": {"from": before, "to": before + 50}}


def test_arming_and_disarming_the_kill_switch_is_recorded():
    client.post("/api/settings", json={"autonomy_kill_switch": False})
    client.post("/api/settings", json={"autonomy_kill_switch": True})

    changes = [event["details"]["changes"]["autonomy_kill_switch"]["to"] for event in events()]
    assert changes[:2] == [True, False]


def test_a_save_that_changes_nothing_adds_no_event():
    current = sqlite_manager.get_settings()["theme"]
    client.post("/api/settings", json={"theme": current})
    assert events() == []


def test_credentials_are_recorded_by_name_and_never_by_value(isolated_db):
    response = client.post("/api/settings", json={"api_keys": {
        "binance_testnet_key": FAKE_SECRET,
        "groq": "",
        "alpaca_key": "********",
    }})
    assert response.status_code == 200

    latest = events()[0]
    assert latest["details"]["credentials"] == {"binance_testnet_key": "set", "groq": "cleared"}
    assert FAKE_SECRET not in client.get("/api/audit").text
    assert FAKE_SECRET.encode() not in isolated_db.read_bytes()


def test_a_failing_audit_write_does_not_block_the_save(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(settings_api, "record_audit_event", broken)
    response = client.post("/api/settings", json={"autonomy_kill_switch": True})
    assert response.status_code == 200


def test_limit_is_bounded_and_newest_comes_first():
    sqlite_manager.record_audit_event("settings", "first")
    sqlite_manager.record_audit_event("settings", "second")

    assert [event["action"] for event in client.get("/api/audit", params={"limit": 1}).json()["items"]] == ["second"]
    assert client.get("/api/audit", params={"limit": 501}).status_code == 422
