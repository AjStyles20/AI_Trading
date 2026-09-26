from core.credential_provider import resolve_api_keys


def test_legacy_settings_remain_compatible(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = {"api_keys": {"openai": "legacy-key", "binance_key": "legacy-binance"}}
    keys = resolve_api_keys(settings)
    assert keys["openai"] == "legacy-key"
    assert keys["binance_key"] == "legacy-binance"


def test_environment_secret_overrides_legacy_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    keys = resolve_api_keys({"api_keys": {"openai": "legacy-key"}})
    assert keys["openai"] == "environment-key"


def test_environment_can_supply_secret_without_sqlite(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "env-binance")
    keys = resolve_api_keys({"api_keys": {}})
    assert keys["binance_key"] == "env-binance"
