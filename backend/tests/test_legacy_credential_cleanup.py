from database import sqlite_manager


def test_remove_legacy_api_keys_removes_only_named_entries(tmp_path, monkeypatch):
    db_path = tmp_path / "astral-cleanup.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    # Seed legacy values directly to represent an installation created before
    # the plaintext-write barrier existed.
    import json
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE settings SET api_keys = ? WHERE id = 1",
        (json.dumps({
            "binance_key": "old-binance",
            "binance_secret": "old-secret",
            "unknown_setting": "preserve-me",
        }),),
    )
    conn.commit()
    conn.close()

    assert sqlite_manager.remove_legacy_api_keys(["binance_key"])
    remaining = sqlite_manager.get_settings()["api_keys"]
    assert "binance_key" not in remaining
    assert remaining["binance_secret"] == "old-secret"
    assert remaining["unknown_setting"] == "preserve-me"


def test_remove_legacy_api_keys_empty_request_is_noop(tmp_path, monkeypatch):
    db_path = tmp_path / "astral-cleanup.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    before = sqlite_manager.get_settings()["api_keys"]
    assert sqlite_manager.remove_legacy_api_keys([])
    assert sqlite_manager.get_settings()["api_keys"] == before
