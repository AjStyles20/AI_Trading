from database import sqlite_manager


def test_equity_state_preserves_peak_and_resets_daily_start(tmp_path, monkeypatch):
    test_db = tmp_path / "astral-risk-test.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(test_db))
    sqlite_manager.init_db()

    first = sqlite_manager.update_risk_equity_state(
        "paper", "paper", 1000.0, trading_day="2026-09-25"
    )
    assert first["day_start_equity"] == 1000.0
    assert first["peak_equity"] == 1000.0

    higher = sqlite_manager.update_risk_equity_state(
        "paper", "paper", 1100.0, trading_day="2026-09-25"
    )
    assert higher["day_start_equity"] == 1000.0
    assert higher["peak_equity"] == 1100.0

    lower = sqlite_manager.update_risk_equity_state(
        "paper", "paper", 950.0, trading_day="2026-09-25"
    )
    assert lower["day_start_equity"] == 1000.0
    assert lower["peak_equity"] == 1100.0

    next_day = sqlite_manager.update_risk_equity_state(
        "paper", "paper", 975.0, trading_day="2026-09-26"
    )
    assert next_day["day_start_equity"] == 975.0
    assert next_day["peak_equity"] == 1100.0

    persisted = sqlite_manager.get_risk_equity_state("paper", "paper")
    assert persisted["trading_day"] == "2026-09-26"
    assert persisted["day_start_equity"] == 975.0
    assert persisted["peak_equity"] == 1100.0
    assert persisted["last_equity"] == 975.0


def test_equity_state_is_isolated_by_broker_and_mode(tmp_path, monkeypatch):
    test_db = tmp_path / "astral-risk-isolation.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(test_db))
    sqlite_manager.init_db()

    sqlite_manager.update_risk_equity_state("paper", "paper", 1000.0, "2026-09-26")
    sqlite_manager.update_risk_equity_state("alpaca", "live", 5000.0, "2026-09-26")

    paper = sqlite_manager.get_risk_equity_state("paper", "paper")
    live = sqlite_manager.get_risk_equity_state("alpaca", "live")
    assert paper["peak_equity"] == 1000.0
    assert live["peak_equity"] == 5000.0
