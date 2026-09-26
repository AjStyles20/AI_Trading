import os

import pytest

from core import credential_provider


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
        target = (service, key)
        if target not in self.values:
            raise self.errors.PasswordDeleteError()
        del self.values[target]


def test_environment_overrides_secure_and_legacy(monkeypatch):
    fake = FakeKeyring()
    fake.set_password(credential_provider.SERVICE_NAME, "openai", "secure")
    monkeypatch.setattr(credential_provider, "_keyring", lambda: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "environment")

    result = credential_provider.resolve_api_keys({"api_keys": {"openai": "legacy"}})

    assert result["openai"] == "environment"


def test_secure_store_overrides_legacy(monkeypatch):
    fake = FakeKeyring()
    fake.set_password(credential_provider.SERVICE_NAME, "openai", "secure")
    monkeypatch.setattr(credential_provider, "_keyring", lambda: fake)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = credential_provider.resolve_api_keys({"api_keys": {"openai": "legacy"}})

    assert result["openai"] == "secure"


def test_secure_credential_can_be_deleted(monkeypatch):
    fake = FakeKeyring()
    fake.set_password(credential_provider.SERVICE_NAME, "openai", "secure")
    monkeypatch.setattr(credential_provider, "_keyring", lambda: fake)

    credential_provider.set_secure_credential("openai", "")

    assert fake.get_password(credential_provider.SERVICE_NAME, "openai") is None


def test_unsupported_credential_key_is_rejected():
    with pytest.raises(ValueError, match="Unsupported credential key"):
        credential_provider.set_secure_credential("unknown_secret", "value")


def test_secure_store_failure_is_fail_closed(monkeypatch):
    class BrokenKeyring(FakeKeyring):
        def set_password(self, service, key, value):
            raise OSError("backend unavailable")

    monkeypatch.setattr(credential_provider, "_keyring", lambda: BrokenKeyring())

    with pytest.raises(RuntimeError, match="could not be updated"):
        credential_provider.set_secure_credential("openai", "secret")
