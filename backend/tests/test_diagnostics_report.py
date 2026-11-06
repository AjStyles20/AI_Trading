import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import sqlite_manager  # noqa: E402
import diagnostics_api  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")
FAKE_SECRET = "test-only-not-a-real-key-5678"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "diag.db"))
    sqlite_manager.init_db()


def test_report_covers_safety_state_records_and_recent_activity(monkeypatch):
    monkeypatch.setattr("core.credential_provider.resolve_api_keys", lambda settings=None: {"groq": FAKE_SECRET})
    sqlite_manager.record_journal_entry("s1", "SIGNAL: BUY")
    sqlite_manager.record_audit_event("settings", "updated", {"changes": {"autonomy_kill_switch": {"from": False, "to": True}}})

    report = client.get("/api/diagnostics/report").json()["report"]

    assert report.startswith("Astral AI diagnostics report")
    assert "App version: 0." in report
    assert "- Kill switch armed: True" in report
    assert "- Live trading enabled: False" in report
    assert "Stored credentials (names only): groq" in report
    assert "- trades: 0" in report and "- trading_journal: 1" in report
    assert "SIGNAL: BUY" in report
    assert "autonomy_kill_switch" in report
    assert FAKE_SECRET not in report


def test_report_hides_the_home_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(os.path, "expanduser", lambda path: str(tmp_path) if path == "~" else path)
    report = diagnostics_api.build_diagnostics_report()
    assert str(tmp_path) not in report
    assert "Data folder: ~" in report
