import pytest

from core import credential_provider


class MemoryKeyring:
    class errors:
        class PasswordDeleteError(Exception):
            pass

    def __init__(self, fail_write=False, fail_read=False):
        self.values = {}
        self.fail_write = fail_write
        self.fail_read = fail_read

    def get_password(self, service, key):
        if self.fail_read:
            raise RuntimeError("read unavailable")
        return self.values.get((service, key))

    def set_password(self, service, key, value):
        if self.fail_write:
            raise RuntimeError("write unavailable")
        self.values[(service, key)] = value


def test_migrate_legacy_credentials_verifies_secure_copy(monkeypatch):
    store = MemoryKeyring()
    monkeypatch.setattr(credential_provider, "_keyring", lambda: store)
    settings = {"api_keys": {"binance_key": "legacy-key", "unknown": "leave-alone"}}

    migrated = credential_provider.migrate_legacy_credentials(settings)

    assert migrated == ["binance_key"]
    assert store.values[(credential_provider.SERVICE_NAME, "binance_key")] == "legacy-key"


def test_migrate_legacy_credentials_fails_closed_on_secure_write(monkeypatch):
    store = MemoryKeyring(fail_write=True)
    monkeypatch.setattr(credential_provider, "_keyring", lambda: store)

    with pytest.raises(RuntimeError):
        credential_provider.migrate_legacy_credentials(
            {"api_keys": {"binance_key": "legacy-key"}}
        )


def test_migrate_legacy_credentials_requires_readback_verification(monkeypatch):
    store = MemoryKeyring(fail_read=True)
    monkeypatch.setattr(credential_provider, "_keyring", lambda: store)

    with pytest.raises(RuntimeError, match="verification failed"):
        credential_provider.migrate_legacy_credentials(
            {"api_keys": {"binance_key": "legacy-key"}}
        )
