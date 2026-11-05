import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import sqlite_manager  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "astral.db"))
    sqlite_manager.init_db()
    return tmp_path


def test_backup_is_a_complete_readable_copy(isolated_db):
    sqlite_manager.create_price_alert("BTC/USDT", "crypto", "above", 90000.0)

    response = client.post("/api/backups")
    assert response.status_code == 200
    body = response.json()
    assert body["folder"] == str(isolated_db / "backups")
    path = isolated_db / "backups" / body["backup"]["name"]

    copy = sqlite3.connect(path)
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert copy.execute("SELECT symbol, price FROM price_alerts").fetchall() == [("BTC/USDT", 90000.0)]
    copy.close()


def test_backup_is_consistent_while_another_connection_has_uncommitted_writes(isolated_db):
    writer = sqlite3.connect(sqlite_manager.DB_PATH)
    writer.execute("INSERT INTO price_alerts (symbol, asset_type, direction, price) VALUES ('X', 'stock', 'above', 1)")
    try:
        name = sqlite_manager.create_backup()["name"]
    finally:
        writer.rollback()
        writer.close()

    copy = sqlite3.connect(isolated_db / "backups" / name)
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert copy.execute("SELECT count(*) FROM price_alerts").fetchone()[0] == 0
    copy.close()


def test_only_the_newest_backups_are_kept(monkeypatch, isolated_db):
    names = [sqlite_manager.create_backup(keep=3)["name"] for _ in range(5)]

    kept = [item["name"] for item in client.get("/api/backups").json()["items"]]
    assert len(kept) == 3
    assert set(kept) == set(names[-3:])
    assert sorted(os.listdir(isolated_db / "backups")) == sorted(kept)


def test_backups_in_the_same_second_get_distinct_names():
    first = sqlite_manager.create_backup()["name"]
    second = sqlite_manager.create_backup()["name"]
    assert first != second


def test_listing_without_any_backups_is_empty():
    assert client.get("/api/backups").json()["items"] == []


def test_a_failed_backup_reports_an_error(monkeypatch):
    import backup_api

    def broken():
        raise OSError("disk full")

    monkeypatch.setattr(backup_api, "create_backup", broken)
    response = client.post("/api/backups")
    assert response.status_code == 500
    assert response.json()["detail"] == "Backup failed: OSError"


def test_pruning_keeps_the_newest_even_within_one_second():
    names = [sqlite_manager.create_backup(keep=2)["name"] for _ in range(4)]
    kept = [item["name"] for item in sqlite_manager.list_backups()]
    assert kept == [names[3], names[2]]
