import pytest

from ai_engine import assistant
from database import sqlite_manager


def test_provider_selection_uses_only_selected_credential_and_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant, "ChatOpenAI", lambda **kwargs: calls.append(kwargs) or object())
    monkeypatch.setattr(assistant, "resolve_api_keys", lambda settings: {"openai": "openai-secret", "groq": "groq-secret"})
    instance = assistant.AstralAIAssistant.__new__(assistant.AstralAIAssistant)

    for provider, model, expected_key, expected_url in (
        ("openai", "gpt-4.1-mini", "openai-secret", None),
        ("groq", "openai/gpt-oss-20b", "groq-secret", "https://api.groq.com/openai/v1"),
        ("ollama", "local-model", "ollama", "http://127.0.0.1:11434/v1"),
    ):
        monkeypatch.setattr(assistant, "get_settings", lambda: {"ai_provider": provider, "ai_model": "local-model" if provider == "ollama" else ""})
        instance._initialize_llm()
        assert instance.get_llm() is not None
        assert instance.model_name == model
        assert calls[-1]["api_key"] == expected_key
        assert calls[-1].get("base_url") == expected_url


def test_missing_selected_key_does_not_fall_back_to_another_provider(monkeypatch):
    monkeypatch.setattr(assistant, "get_settings", lambda: {"ai_provider": "groq", "ai_model": ""})
    monkeypatch.setattr(assistant, "resolve_api_keys", lambda settings: {"openai": "openai-secret"})
    instance = assistant.AstralAIAssistant.__new__(assistant.AstralAIAssistant)
    instance._initialize_llm()
    assert instance.get_llm() is None


def test_provider_settings_migrate_and_validate(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "settings.db"))
    sqlite_manager.init_db()
    assert sqlite_manager.get_settings()["ai_provider"] == "openai"
    assert sqlite_manager.update_settings(ai_provider="ollama", ai_model="local-model")
    sqlite_manager.init_db()
    assert sqlite_manager.get_public_settings()["ai_model"] == "local-model"
    assert sqlite_manager.get_settings()["ai_provider"] == "ollama"
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        sqlite_manager.update_settings(ai_provider="unknown")
