import pytest

from database import sqlite_manager


def test_broker_environment_defaults_and_updates(tmp_path, monkeypatch):
    db_path = tmp_path / "astral-test.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    initial = sqlite_manager.get_settings()
    assert initial["binance_environment"] == "live"
    assert initial["bitget_environment"] == "live"

    assert sqlite_manager.update_settings(
        binance_environment="testnet",
        bitget_environment="demo",
    )
    updated = sqlite_manager.get_settings()
    assert updated["binance_environment"] == "testnet"
    assert updated["bitget_environment"] == "demo"
    assert updated["risk_max_order_notional"] == initial["risk_max_order_notional"]
    assert updated["theme"] == initial["theme"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("binance_environment", "paper"),
        ("binance_environment", ""),
        ("bitget_environment", "testnet"),
        ("bitget_environment", "sandbox"),
    ],
)
def test_broker_environment_rejects_invalid_values(tmp_path, monkeypatch, field, value):
    db_path = tmp_path / "astral-test.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    with pytest.raises(ValueError):
        sqlite_manager.update_settings(**{field: value})

    current = sqlite_manager.get_settings()
    assert current["binance_environment"] == "live"
    assert current["bitget_environment"] == "live"
