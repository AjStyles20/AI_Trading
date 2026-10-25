import base64
import os
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

import main  # noqa: E402
from ai_engine import assistant, attachments  # noqa: E402
from database import sqlite_manager  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1:8000")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


def data_url(kind: str, data: bytes) -> str:
    return f"data:image/{kind};base64,{base64.b64encode(data).decode()}"


# --- validation -----------------------------------------------------------

@pytest.mark.parametrize("kind, data", [("png", PNG), ("jpeg", JPEG), ("gif", GIF), ("webp", WEBP)])
def test_real_images_are_accepted(kind, data):
    url = data_url(kind, data)
    assert attachments.validate_image_data_urls([url]) == [url]


@pytest.mark.parametrize("url, reason", [
    ("https://example.com/chart.png", "not a supported image"),
    ("data:image/svg+xml;base64,PHN2Zz4=", "not a supported image"),
    ("data:text/html;base64,PGh0bWw+", "not a supported image"),
    (data_url("png", JPEG), "does not contain the image type"),
    (data_url("jpeg", b"MZ\x90\x00 not an image"), "does not contain the image type"),
    ("data:image/png;base64,***", "not a supported image"),
])
def test_anything_else_is_rejected(url, reason):
    with pytest.raises(ValueError, match=reason):
        attachments.validate_image_data_urls([url])


def test_count_and_size_limits(monkeypatch):
    with pytest.raises(ValueError, match="at most 4"):
        attachments.validate_image_data_urls([data_url("png", PNG)] * 5)
    monkeypatch.setattr(attachments, "MAX_IMAGE_BYTES", 16)
    with pytest.raises(ValueError, match="larger than"):
        attachments.validate_image_data_urls([data_url("png", PNG)])


def test_total_size_limit(monkeypatch):
    monkeypatch.setattr(attachments, "MAX_TOTAL_BYTES", len(PNG) * 2)
    with pytest.raises(ValueError, match="in total"):
        attachments.validate_image_data_urls([data_url("png", PNG)] * 3)


# --- endpoint ---------------------------------------------------------------

def test_chat_rejects_invalid_images_before_calling_the_ai(monkeypatch):
    called = []
    monkeypatch.setattr(main.ai_assistant, "analyze_market_query", lambda *args: called.append(args) or "x")
    response = client.post("/api/chat", json={"query": "look", "images": ["data:text/html;base64,PGh0bWw+"]})

    assert response.status_code == 400
    assert "not a supported image" in response.json()["detail"]
    assert called == []


def test_chat_passes_validated_images_to_the_assistant(monkeypatch):
    received = []
    monkeypatch.setattr(main.ai_assistant, "analyze_market_query",
                        lambda query, conversation_id, images: received.append((query, images)) or "seen")
    url = data_url("png", PNG)
    response = client.post("/api/chat", json={"query": "what is this?", "conversation_id": "c1", "images": [url]})

    assert response.json() == {"response": "seen", "status": "success"}
    assert received == [("what is this?", [url])]


# --- assistant ----------------------------------------------------------------

class FakeLLM:
    def __init__(self, reply="A rising wedge."):
        self.reply = reply
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Reply", (), {"content": self.reply})()


class FakeMemory:
    def __init__(self):
        self.remembered = []

    def recall_conversations(self, query, n_results=2):
        return {"documents": [[]]}

    def remember_conversation(self, doc_id, text, metadata):
        self.remembered.append(text)


@pytest.fixture
def chat_assistant(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "chat.db"))
    sqlite_manager.init_db()
    instance = assistant.AstralAIAssistant.__new__(assistant.AstralAIAssistant)
    instance.memory_manager = FakeMemory()
    instance._initialized = True
    instance.llm = FakeLLM("text reply")
    instance.vision_llm = FakeLLM("A rising wedge.")
    return instance


def test_images_go_to_the_vision_model_and_are_not_stored(chat_assistant):
    url = data_url("png", PNG)
    reply = chat_assistant.analyze_market_query("What pattern is this?", "c1", [url])

    assert reply == "A rising wedge."
    assert chat_assistant.llm.calls == []
    content = chat_assistant.vision_llm.calls[0][-1].content
    assert content[0] == {"type": "text", "text": "What pattern is this?"}
    assert content[1] == {"type": "image_url", "image_url": {"url": url}}

    stored = sqlite_manager.get_recent_chat_messages("c1")
    assert stored[0]["content"] == "What pattern is this?\n\n[1 image attached]"
    assert url not in "".join(m["content"] for m in stored)
    assert all(url not in text for text in chat_assistant.memory_manager.remembered)


def test_text_messages_keep_using_the_chat_model(chat_assistant):
    assert chat_assistant.analyze_market_query("hello", "c1") == "text reply"
    assert chat_assistant.vision_llm.calls == []
    assert chat_assistant.llm.calls[0][-1].content == "hello"


def test_images_without_a_vision_model_explain_how_to_set_one(chat_assistant):
    chat_assistant.vision_llm = None
    reply = chat_assistant.analyze_market_query("look", "c1", [data_url("png", PNG)])
    assert "vision-capable model" in reply
    assert chat_assistant.llm.calls == []


def test_vision_model_defaults_and_settings(monkeypatch):
    created = []
    monkeypatch.setattr(assistant, "ChatOpenAI", lambda **kwargs: created.append(kwargs["model"]) or object())
    monkeypatch.setattr(assistant, "resolve_api_keys", lambda settings: {"openai": "k", "groq": "k"})
    instance = assistant.AstralAIAssistant.__new__(assistant.AstralAIAssistant)

    # OpenAI chat models read images, so the chat model doubles as the vision model.
    monkeypatch.setattr(assistant, "get_settings", lambda: {"ai_provider": "openai", "ai_model": "", "ai_vision_model": ""})
    instance._initialize_llm()
    assert instance.get_vision_llm() is not None and instance.vision_model_name == "gpt-4.1-mini"

    # Groq needs an explicitly chosen vision model.
    monkeypatch.setattr(assistant, "get_settings", lambda: {"ai_provider": "groq", "ai_model": "", "ai_vision_model": ""})
    instance._initialize_llm()
    assert instance.get_vision_llm() is None

    monkeypatch.setattr(assistant, "get_settings", lambda: {"ai_provider": "groq", "ai_model": "", "ai_vision_model": "vision-x"})
    instance._initialize_llm()
    assert instance.get_vision_llm() is not None and created[-1] == "vision-x"


def test_vision_model_setting_is_stored_and_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "settings.db"))
    sqlite_manager.init_db()
    assert sqlite_manager.get_settings()["ai_vision_model"] == ""
    sqlite_manager.update_settings(ai_vision_model="  vision-x  ")
    assert sqlite_manager.get_public_settings()["ai_vision_model"] == "vision-x"
    with pytest.raises(ValueError, match="Invalid AI vision model name"):
        sqlite_manager.update_settings(ai_vision_model="bad\nname")
