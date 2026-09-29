from fastapi.testclient import TestClient
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main


client = TestClient(main.app, base_url="http://127.0.0.1:8000")


def test_missing_key_never_returns_an_unrelated_example_strategy(monkeypatch):
    monkeypatch.setattr(main.ai_assistant, "get_llm", lambda: None)
    for endpoint, payload in (
        ("/api/strategy", {"prompt": "Buy on a Bollinger breakout"}),
        ("/api/strategy/build", {"nodes": [{"id": "rsi", "type": "RSI"}], "edges": []}),
    ):
        response = client.post(endpoint, json=payload)
        assert response.status_code == 503
        assert "AI provider" in response.json()["detail"]


def test_graph_export_initializes_the_configured_model(monkeypatch):
    calls = []

    def get_llm():
        calls.append("initialized")
        return object()

    class FakeGenerator:
        def __init__(self, llm):
            assert llm is not None

        def generate_from_graph(self, nodes, edges):
            return "def strategy(df):\n    return df"

    monkeypatch.setattr(main.ai_assistant, "get_llm", get_llm)
    monkeypatch.setattr(main, "StrategyGenerator", FakeGenerator)
    response = client.post("/api/strategy/build", json={"nodes": [], "edges": []})
    assert response.status_code == 200
    assert response.json()["generation_mode"] == "ai"
    assert calls == ["initialized"]
