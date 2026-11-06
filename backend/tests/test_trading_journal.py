import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import sqlite_manager  # noqa: E402
import backend.trading_api as trading_api  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "journal.db"))
    sqlite_manager.init_db()


def test_tests_never_use_the_real_data_folder():
    # conftest.py must take effect before the database module is imported.
    assert "astral-tests-" in os.environ["ASTRAL_DATA_DIR"]


def test_log_lines_outlive_the_manager_and_keep_their_session():
    manager = trading_api.LiveTradingManager()
    manager.session_id = "2026-11-02 10:00:00"
    manager.log("SIGNAL: BUY")

    # A new manager has no memory of it, as after a restart; the journal does.
    assert trading_api.LiveTradingManager().logs == []
    latest = client.get("/api/trading/journal").json()["items"][0]
    assert latest["message"] == "SIGNAL: BUY"
    assert latest["session_id"] == "2026-11-02 10:00:00"


def test_a_failing_journal_write_never_reaches_the_loop(monkeypatch):
    def broken(*args):
        raise OSError("database is locked")

    monkeypatch.setattr(trading_api, "record_journal_entry", broken)
    manager = trading_api.LiveTradingManager()

    manager.log("AUTONOMY PAUSED")

    assert manager.logs[-1].endswith("AUTONOMY PAUSED")


def test_memory_log_stays_short_while_the_journal_keeps_more():
    manager = trading_api.LiveTradingManager()
    for index in range(60):
        manager.log(f"line {index}")

    assert len(manager.logs) == 50
    assert len(client.get("/api/trading/journal", params={"limit": 100}).json()["items"]) == 60


def test_journal_is_pruned_and_newest_comes_first(monkeypatch):
    monkeypatch.setattr(sqlite_manager, "JOURNAL_MAX_ROWS", 3)
    for index in range(5):
        sqlite_manager.record_journal_entry(None, f"line {index}")

    items = client.get("/api/trading/journal").json()["items"]
    assert [item["message"] for item in items] == ["line 4", "line 3", "line 2"]
    assert client.get("/api/trading/journal", params={"limit": 1001}).status_code == 422
