import pytest

from database import sqlite_manager


def test_new_credentials_are_not_written_to_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "settings.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    with pytest.raises(ValueError, match="Refusing to persist credential"):
        sqlite_manager.update_settings(api_keys={"openai": "sk-new-secret"})

    assert sqlite_manager.get_settings()["api_keys"] == {}


def test_masked_placeholder_preserves_legacy_credential(tmp_path, monkeypatch):
    db_path = tmp_path / "settings.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    conn = sqlite_manager.sqlite3.connect(sqlite_manager.DB_PATH)
    conn.execute("UPDATE settings SET api_keys = ? WHERE id = 1", ('{"openai":"legacy-secret"}',))
    conn.commit()
    conn.close()

    sqlite_manager.update_settings(api_keys={"openai": "********"}, theme="light")

    settings = sqlite_manager.get_settings()
    assert settings["api_keys"]["openai"] == "legacy-secret"
    assert settings["theme"] == "light"
    assert sqlite_manager.get_public_settings()["api_keys"]["openai"] == "********"


def test_empty_credential_removes_legacy_value(tmp_path, monkeypatch):
    db_path = tmp_path / "settings.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    conn = sqlite_manager.sqlite3.connect(sqlite_manager.DB_PATH)
    conn.execute("UPDATE settings SET api_keys = ? WHERE id = 1", ('{"openai":"legacy-secret"}',))
    conn.commit()
    conn.close()

    sqlite_manager.update_settings(api_keys={"openai": ""})

    assert "openai" not in sqlite_manager.get_settings()["api_keys"]
