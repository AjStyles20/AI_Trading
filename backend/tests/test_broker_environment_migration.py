import json
import sqlite3

from database import sqlite_manager


def test_init_db_migrates_legacy_broker_environment_flags(tmp_path, monkeypatch):
    db_path = tmp_path / "astral-legacy.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            api_keys TEXT,
            theme TEXT DEFAULT 'dark',
            paper_trading BOOLEAN DEFAULT 1
        )
        """
    )
    legacy = {
        "binance_testnet": "true",
        "bitget_demo": "1",
        "binance_key": "legacy-secret-that-must-remain",
    }
    conn.execute(
        "INSERT INTO settings (id, api_keys, theme, paper_trading) VALUES (1, ?, 'dark', 1)",
        (json.dumps(legacy),),
    )
    conn.commit()
    conn.close()

    sqlite_manager.init_db()
    settings = sqlite_manager.get_settings()

    assert settings["binance_environment"] == "testnet"
    assert settings["bitget_environment"] == "demo"
    assert "binance_testnet" not in settings["api_keys"]
    assert "bitget_demo" not in settings["api_keys"]
    assert settings["api_keys"]["binance_key"] == "legacy-secret-that-must-remain"

    # Migration must be idempotent.
    sqlite_manager.init_db()
    again = sqlite_manager.get_settings()
    assert again["binance_environment"] == "testnet"
    assert again["bitget_environment"] == "demo"
    assert again["api_keys"]["binance_key"] == "legacy-secret-that-must-remain"
