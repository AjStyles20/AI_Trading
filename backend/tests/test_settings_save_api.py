"""The Settings form's save payload, end to end through POST /api/settings."""
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from core import credential_provider  # noqa: E402
from database import sqlite_manager  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")

# Every credential slot the Settings form sends.
FORM_KEYS = [
    "openai", "groq",
    "binance_key", "binance_secret", "binance_testnet_key", "binance_testnet_secret",
    "bitget_key", "bitget_secret", "bitget_passphrase",
    "bitget_demo_key", "bitget_demo_secret", "bitget_demo_passphrase",
    "alpaca_key", "alpaca_secret", "alpaca_paper_key", "alpaca_paper_secret",
]


class FakeErrors:
    class PasswordDeleteError(Exception):
        pass


class FakeKeyring:
    errors = FakeErrors

    def __init__(self):
        self.values = {}

    def get_password(self, service, key):
        return self.values.get((service, key))

    def set_password(self, service, key, value):
        self.values[(service, key)] = value

    def delete_password(self, service, key):
        if (service, key) not in self.values:
            raise self.errors.PasswordDeleteError()
        del self.values[(service, key)]


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "settings.db"))
    sqlite_manager.init_db()
    store = FakeKeyring()
    monkeypatch.setattr(credential_provider, "_keyring", lambda: store)
    for env_name in credential_provider.ENV_KEY_MAP.values():
        monkeypatch.delenv(env_name, raising=False)
    return store


def _stored(store, key):
    return store.get_password(credential_provider.SERVICE_NAME, key)


def test_form_save_keeps_stored_keys_and_saves_broker_environments(tmp_path, monkeypatch):
    store = _isolate(tmp_path, monkeypatch)
    store.set_password(credential_provider.SERVICE_NAME, "binance_testnet_key", "stored-testnet-key")
    store.set_password(credential_provider.SERVICE_NAME, "alpaca_paper_secret", "stored-paper-secret")

    # What the form now sends: present keys masked, absent keys empty, and the
    # broker environments as their own settings fields.
    presence = client.get("/api/settings").json()["credential_presence"]
    api_keys = {key: "********" if presence.get(key) else "" for key in FORM_KEYS}
    response = client.post("/api/settings", json={
        "ai_provider": "groq",
        "ai_model": "",
        "binance_environment": "testnet",
        "bitget_environment": "demo",
        "api_keys": api_keys,
    })

    assert response.status_code == 200, response.text
    assert _stored(store, "binance_testnet_key") == "stored-testnet-key"
    assert _stored(store, "alpaca_paper_secret") == "stored-paper-secret"
    saved = client.get("/api/settings").json()
    assert saved["binance_environment"] == "testnet"
    assert saved["bitget_environment"] == "demo"
    assert saved["ai_provider"] == "groq"
    assert saved["credential_presence"]["binance_testnet_key"] is True
    assert saved["credential_presence"]["alpaca_paper_secret"] is True


def test_legacy_environment_flags_in_api_keys_are_rejected(tmp_path, monkeypatch):
    """The old form sent the switches as fake credentials; the backend must refuse
    them rather than store unknown names in the credential store."""
    store = _isolate(tmp_path, monkeypatch)
    response = client.post("/api/settings", json={
        "api_keys": {"binance_testnet": "true", "bitget_demo": "false"},
    })

    assert response.status_code == 400
    assert "Unsupported credential key" in response.json()["detail"]
    assert store.values == {}


def test_invalid_environment_value_is_rejected_with_a_reason(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    response = client.post("/api/settings", json={"binance_environment": "mainnet"})

    assert response.status_code == 400
    assert "binance_environment" in response.json()["detail"]
