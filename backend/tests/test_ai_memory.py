import os
import sys

import chromadb
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from database.vector_manager import VectorMemoryManager  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1:8000")


@pytest.fixture
def memory(tmp_path, monkeypatch):
    manager = VectorMemoryManager(client=chromadb.PersistentClient(path=str(tmp_path / "chroma")))
    # Fixed vectors: no embedding model is downloaded or run.
    manager.conversations.add(
        ids=["old", "newer", "newest"],
        documents=["User asked: likes RSI", "User asked: BTC trend", "User asked: gold"],
        metadatas=[
            {"topic": "market_analysis"},
            {"topic": "market_analysis", "created_at": "2026-11-01 10:00:00"},
            {"topic": "market_analysis", "created_at": "2026-11-05 09:00:00"},
        ],
        embeddings=[[0.1, 0.2, 0.3], [0.2, 0.1, 0.3], [0.3, 0.2, 0.1]],
    )
    monkeypatch.setattr(main.ai_assistant, "memory_manager", manager)
    return manager


def test_memories_are_listed_newest_first_with_undated_ones_last(memory):
    body = client.get("/api/ai/memory").json()

    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == ["newest", "newer", "old"]
    assert body["items"][0]["text"] == "User asked: gold"
    assert body["items"][2]["created_at"] is None


def test_one_memory_can_be_forgotten(memory):
    assert client.delete("/api/ai/memory/newer").status_code == 200

    assert [item["id"] for item in memory.list_memories()] == ["newest", "old"]
    assert client.delete("/api/ai/memory/newer").status_code == 404


def test_forgetting_everything_needs_explicit_confirmation(memory):
    assert client.post("/api/ai/memory/forget-all", json={}).status_code == 400
    assert memory.count_memories() == 3

    response = client.post("/api/ai/memory/forget-all", json={"confirm": True})
    assert response.json() == {"forgotten": 3}
    assert memory.count_memories() == 0
    assert client.post("/api/ai/memory/forget-all", json={"confirm": True}).json() == {"forgotten": 0}


def test_limit_is_bounded(memory):
    assert len(client.get("/api/ai/memory", params={"limit": 1}).json()["items"]) == 1
    assert client.get("/api/ai/memory", params={"limit": 1001}).status_code == 422
