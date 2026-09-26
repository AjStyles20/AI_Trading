from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import settings_api


app = FastAPI()
app.include_router(settings_api.router)
client = TestClient(app)


def test_credential_migration_cleans_only_verified_keys(monkeypatch):
    monkeypatch.setattr(
        settings_api,
        "get_settings",
        lambda: {"api_keys": {"binance_key": "legacy", "binance_secret": "keep"}},
    )
    monkeypatch.setattr(
        settings_api,
        "migrate_legacy_credentials",
        lambda settings: ["binance_key"],
    )
    cleaned = []
    monkeypatch.setattr(
        settings_api,
        "remove_legacy_api_keys",
        lambda keys: cleaned.extend(keys) or True,
    )

    response = client.post("/api/settings/migrate-credentials")

    assert response.status_code == 200
    assert response.json()["migrated"] == ["binance_key"]
    assert response.json()["migrated_count"] == 1
    assert cleaned == ["binance_key"]


def test_credential_migration_does_not_cleanup_on_secure_failure(monkeypatch):
    monkeypatch.setattr(settings_api, "get_settings", lambda: {"api_keys": {"binance_key": "legacy"}})

    def fail(_settings):
        raise RuntimeError("OS credential store could not be updated.")

    monkeypatch.setattr(settings_api, "migrate_legacy_credentials", fail)
    cleanup_called = []
    monkeypatch.setattr(
        settings_api,
        "remove_legacy_api_keys",
        lambda keys: cleanup_called.append(keys) or True,
    )

    response = client.post("/api/settings/migrate-credentials")

    assert response.status_code == 400
    assert cleanup_called == []
