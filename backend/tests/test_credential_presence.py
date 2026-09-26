from core import credential_provider


class FakeKeyring:
    class errors:
        class PasswordDeleteError(Exception):
            pass

    def __init__(self, values=None):
        self.values = values or {}

    def get_password(self, service, key):
        return self.values.get((service, key))


def test_credential_presence_reports_only_booleans(monkeypatch):
    fake = FakeKeyring({
        (credential_provider.SERVICE_NAME, "binance_key"): "secure-binance-key",
    })
    monkeypatch.setattr(credential_provider, "_keyring", lambda: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "environment-openai-secret")

    legacy = {"api_keys": {"alpaca_key": "legacy-alpaca-secret"}}
    presence = credential_provider.credential_presence(legacy)

    assert presence["openai"] is True
    assert presence["binance_key"] is True
    assert presence["alpaca_key"] is True
    assert presence["bitget_key"] is False
    assert all(isinstance(value, bool) for value in presence.values())
    serialized = repr(presence)
    assert "environment-openai-secret" not in serialized
    assert "secure-binance-key" not in serialized
    assert "legacy-alpaca-secret" not in serialized
