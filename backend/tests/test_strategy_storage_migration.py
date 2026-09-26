import sqlite3

from database import sqlite_manager as db


def test_strategy_schema_migrates_legacy_database(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, symbol TEXT, asset_type TEXT,
            tags TEXT DEFAULT '[]', builder_graph TEXT DEFAULT '{}',
            validation_summary TEXT DEFAULT '{}', optimization_summary TEXT DEFAULT '{}',
            is_baseline BOOLEAN DEFAULT 0, is_archived BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO strategies (name, code) VALUES (?, ?)", ("Old", "def strategy(df): return df"))
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    row = db.get_strategy(1)
    assert row["strategy_format"] == "legacy_python"
    assert row["strategy_spec"] == {}
    assert row["code"].startswith("def strategy")


def test_declarative_strategy_round_trip_and_duplicate(tmp_path, monkeypatch):
    path = tmp_path / "strategies.db"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    spec = {
        "schema_version": 1,
        "strategy_type": "sma_cross",
        "params": {
            "sma_fast": 2, "sma_slow": 4,
            "position_size_pct": 50,
            "stop_loss_pct": 2, "take_profit_pct": 4,
        },
    }
    strategy_id = db.save_strategy(name="Declarative", code="", strategy_spec=spec)
    saved = db.get_strategy(strategy_id)
    assert saved["strategy_format"] == "declarative_v1"
    assert saved["strategy_spec"] == spec
    assert saved["code"] == ""

    duplicate_id = db.duplicate_strategy(strategy_id)
    duplicate = db.get_strategy(duplicate_id)
    assert duplicate["strategy_format"] == "declarative_v1"
    assert duplicate["strategy_spec"] == spec
    assert duplicate["code"] == ""
