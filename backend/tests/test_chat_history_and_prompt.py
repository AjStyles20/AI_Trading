import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from ai_engine.assistant import build_chat_system_prompt  # noqa: E402
from ai_engine.strategy_generator import STRATEGY_SYSTEM_PROMPT  # noqa: E402
from database import sqlite_manager  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")


def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "chat.db"))
    sqlite_manager.init_db()


def test_chat_history_returns_one_conversation_oldest_first(tmp_path, monkeypatch):
    _isolated_db(tmp_path, monkeypatch)
    sqlite_manager.record_chat_message("main", "user", "first question")
    sqlite_manager.record_chat_message("main", "assistant", "first answer")
    sqlite_manager.record_chat_message("other", "user", "unrelated")
    sqlite_manager.record_chat_message("main", "user", "second question")

    response = client.get("/api/chat/history", params={"conversation_id": "main"})

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "main"
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "second question"),
    ]


def test_chat_history_limit_keeps_the_most_recent_messages(tmp_path, monkeypatch):
    _isolated_db(tmp_path, monkeypatch)
    for i in range(5):
        sqlite_manager.record_chat_message("main", "user", f"message {i}")

    messages = client.get("/api/chat/history", params={"conversation_id": "main", "limit": 2}).json()["messages"]

    assert [m["content"] for m in messages] == ["message 3", "message 4"]


def test_chat_history_rejects_out_of_range_limits():
    assert client.get("/api/chat/history", params={"limit": 0}).status_code == 422
    assert client.get("/api/chat/history", params={"limit": 1001}).status_code == 422


def test_chat_prompt_describes_astral_strategies_not_external_frameworks():
    prompt = build_chat_system_prompt()

    assert "strategy(df)" in prompt
    for column in ("signal", "position_size_pct", "stop_loss_pct", "take_profit_pct", "cooldown_bars"):
        assert column in prompt
    assert "Never write VectorBT" in prompt
    assert "using Python and VectorBT" not in prompt
    # Without live data the assistant must not invent current prices.
    assert "Without that section you cannot see live prices" in prompt
    assert "Never invent current prices" in prompt
    assert "cannot place, change or cancel trades" in prompt


def test_chat_prompt_keeps_memory_and_history_context():
    prompt = build_chat_system_prompt("Past Context: likes RSI", "Recent Conversation: USER: hi")

    assert "Past Context: likes RSI" in prompt
    assert "Recent Conversation: USER: hi" in prompt


def test_strategy_generator_asks_for_stop_loss_and_take_profit_columns():
    assert "stop_loss_pct" in STRATEGY_SYSTEM_PROMPT
    assert "take_profit_pct" in STRATEGY_SYSTEM_PROMPT
