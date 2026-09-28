import sqlite3

from database import sqlite_manager


def test_new_database_defaults_kill_switch_armed(tmp_path, monkeypatch):
    db_path = tmp_path / "astral-test.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))

    sqlite_manager.init_db()

    settings = sqlite_manager.get_settings()
    assert settings["autonomy_kill_switch"] is True


def test_legacy_database_migration_adds_armed_kill_switch(tmp_path, monkeypatch):
    db_path = tmp_path / "astral-legacy.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            api_keys TEXT,
            theme TEXT DEFAULT 'dark',
            paper_trading BOOLEAN DEFAULT 1,
            risk_live_trading_enabled BOOLEAN DEFAULT 0,
            risk_max_order_notional REAL DEFAULT 1000.0,
            risk_max_position_pct REAL DEFAULT 25.0,
            risk_max_daily_loss_pct REAL DEFAULT 3.0,
            risk_max_drawdown_pct REAL DEFAULT 10.0,
            binance_environment TEXT DEFAULT 'live',
            bitget_environment TEXT DEFAULT 'live'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO settings (
            id, api_keys, theme, paper_trading, risk_live_trading_enabled,
            risk_max_order_notional, risk_max_position_pct,
            risk_max_daily_loss_pct, risk_max_drawdown_pct,
            binance_environment, bitget_environment
        ) VALUES (1, '{}', 'light', 1, 1, 4321.0, 17.0, 4.0, 11.0, 'testnet', 'demo')
        """
    )
    conn.commit()
    conn.close()

    sqlite_manager.init_db()
    settings = sqlite_manager.get_settings()

    assert settings["autonomy_kill_switch"] is True
    assert settings["theme"] == "light"
    assert settings["risk_live_trading_enabled"] is True
    assert settings["risk_max_order_notional"] == 4321.0
    assert settings["risk_max_position_pct"] == 17.0
    assert settings["risk_max_daily_loss_pct"] == 4.0
    assert settings["risk_max_drawdown_pct"] == 11.0
    assert settings["binance_environment"] == "testnet"
    assert settings["bitget_environment"] == "demo"


def test_kill_switch_disarm_and_rearm_persist_without_field_shift(tmp_path, monkeypatch):
    db_path = tmp_path / "astral-test.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    assert sqlite_manager.update_settings(
        autonomy_kill_switch=False,
        risk_max_order_notional=2500.0,
        risk_max_position_pct=12.5,
        risk_max_daily_loss_pct=2.5,
        risk_max_drawdown_pct=8.0,
        binance_environment="testnet",
        bitget_environment="demo",
    )
    disarmed = sqlite_manager.get_settings()

    assert disarmed["autonomy_kill_switch"] is False
    assert disarmed["risk_max_order_notional"] == 2500.0
    assert disarmed["risk_max_position_pct"] == 12.5
    assert disarmed["risk_max_daily_loss_pct"] == 2.5
    assert disarmed["risk_max_drawdown_pct"] == 8.0
    assert disarmed["binance_environment"] == "testnet"
    assert disarmed["bitget_environment"] == "demo"

    assert sqlite_manager.update_settings(autonomy_kill_switch=True)
    rearmed = sqlite_manager.get_settings()

    assert rearmed["autonomy_kill_switch"] is True
    assert rearmed["risk_max_order_notional"] == 2500.0
    assert rearmed["risk_max_position_pct"] == 12.5
    assert rearmed["risk_max_daily_loss_pct"] == 2.5
    assert rearmed["risk_max_drawdown_pct"] == 8.0
    assert rearmed["binance_environment"] == "testnet"
    assert rearmed["bitget_environment"] == "demo"
