"""Credential access abstraction.

Resolution order is environment variable -> OS credential store -> legacy
SQLite settings. New credentials must be written to the OS credential store;
legacy SQLite credentials remain read-only during migration.
"""
from __future__ import annotations

import os
from typing import Mapping

SERVICE_NAME = "AstralAI"

ENV_KEY_MAP = {
    "openai": "OPENAI_API_KEY",
    "alpaca_key": "ALPACA_API_KEY",
    "alpaca_secret": "ALPACA_API_SECRET",
    "alpaca_paper_key": "ALPACA_PAPER_API_KEY",
    "alpaca_paper_secret": "ALPACA_PAPER_API_SECRET",
    "binance_key": "BINANCE_API_KEY",
    "binance_secret": "BINANCE_API_SECRET",
    "binance_testnet_key": "BINANCE_TESTNET_API_KEY",
    "binance_testnet_secret": "BINANCE_TESTNET_API_SECRET",
    "bitget_key": "BITGET_API_KEY",
    "bitget_secret": "BITGET_API_SECRET",
    "bitget_passphrase": "BITGET_API_PASSPHRASE",
    "bitget_demo_key": "BITGET_DEMO_API_KEY",
    "bitget_demo_secret": "BITGET_DEMO_API_SECRET",
    "bitget_demo_passphrase": "BITGET_DEMO_API_PASSPHRASE",
}


def _keyring():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError(
            "Secure credential storage is unavailable because the keyring package is not installed."
        ) from exc
    return keyring


def get_secure_credential(key: str) -> str | None:
    if key not in ENV_KEY_MAP:
        return None
    try:
        return _keyring().get_password(SERVICE_NAME, key)
    except Exception:
        # Reads remain compatible with environment variables and legacy
        # SQLite credentials on headless systems without a keyring backend.
        # Writes still fail closed in set_secure_credential().
        return None


def set_secure_credential(key: str, value: str) -> None:
    if key not in ENV_KEY_MAP:
        raise ValueError(f"Unsupported credential key: {key}")
    value = str(value or "")
    try:
        store = _keyring()
        if value:
            store.set_password(SERVICE_NAME, key, value)
        else:
            try:
                store.delete_password(SERVICE_NAME, key)
            except store.errors.PasswordDeleteError:
                pass
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("OS credential store could not be updated.") from exc


def resolve_api_keys(settings: Mapping | None = None) -> dict[str, str]:
    """Resolve credentials without exposing their source to callers."""
    legacy = dict((settings or {}).get("api_keys", {}) or {})
    resolved = dict(legacy)

    for key, env_name in ENV_KEY_MAP.items():
        env_value = os.environ.get(env_name)
        if env_value:
            resolved[key] = env_value
            continue
        secure_value = get_secure_credential(key)
        if secure_value:
            resolved[key] = secure_value

    return resolved


def credential_presence(settings: Mapping | None = None) -> dict[str, bool]:
    """Report configured credential slots without returning secret material."""
    resolved = resolve_api_keys(settings)
    return {key: bool(resolved.get(key)) for key in ENV_KEY_MAP}


def migrate_legacy_credentials(settings: Mapping | None = None) -> list[str]:
    """Copy legacy SQLite credentials to the OS store, verifying each write.

    This function never edits SQLite itself. The caller may remove only the
    returned keys from legacy storage after this function succeeds.
    Environment variables are intentionally ignored: they are already secure
    external configuration and should not cause deletion of a legacy value.
    """
    legacy = dict((settings or {}).get("api_keys", {}) or {})
    migrated: list[str] = []
    for key, value in legacy.items():
        if key not in ENV_KEY_MAP or not value or value == "********":
            continue
        existing = get_secure_credential(key)
        if existing == value:
            migrated.append(key)
            continue
        set_secure_credential(key, str(value))
        verified = get_secure_credential(key)
        if verified != str(value):
            raise RuntimeError(f"Secure credential verification failed for '{key}'.")
        migrated.append(key)
    return migrated
