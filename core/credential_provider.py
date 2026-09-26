"""Credential access abstraction.

Environment variables take precedence over legacy SQLite settings. This keeps
credential consumers independent from the storage backend and provides a safe
migration path toward OS-backed secret storage.
"""
from __future__ import annotations

import os
from typing import Mapping


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


def resolve_api_keys(settings: Mapping | None = None) -> dict[str, str]:
    """Resolve credentials without exposing their source to callers."""
    legacy = dict((settings or {}).get("api_keys", {}) or {})
    resolved = dict(legacy)
    for key, env_name in ENV_KEY_MAP.items():
        env_value = os.environ.get(env_name)
        if env_value:
            resolved[key] = env_value
    return resolved
