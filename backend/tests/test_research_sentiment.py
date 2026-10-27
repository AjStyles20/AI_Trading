from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.research_service import research_service

NEWS = [{"title": "Company beats estimates"}, {"title": "Guidance raised"}]


class FakeLLM:
    def __init__(self, content):
        self.content = content

    def invoke(self, messages):
        return SimpleNamespace(content=self.content)


def test_without_a_provider_there_is_no_score_and_no_provider_call():
    # This used to report an invented "Neutral" score of 0.5.
    with patch("core.research_service.yf.Ticker") as ticker:
        result = research_service.get_sentiment_analysis("AAPL", llm=None)
    assert result["status"] == "needs_ai"
    assert result["sentiment_score"] is None
    assert "No AI provider" in result["reason"]
    ticker.assert_not_called()


def test_without_headlines_there_is_no_score():
    with patch("core.research_service.yf.Ticker") as ticker:
        ticker.return_value.news = []
        result = research_service.get_sentiment_analysis("AAPL", llm=FakeLLM('{"score": 0.9, "label": "Bullish"}'))
    assert result["status"] == "unavailable"
    assert result["sentiment_score"] is None


@pytest.mark.parametrize("content", [
    "not json",
    '{"score": 1.7, "label": "Bullish"}',
    '{"score": "NaN", "label": "Bullish"}',
    '{"score": 0.4, "label": "To the moon"}',
    '{"label": "Bullish"}',
])
def test_unusable_model_answers_are_reported_not_replaced(content):
    with patch("core.research_service.yf.Ticker") as ticker:
        ticker.return_value.news = NEWS
        result = research_service.get_sentiment_analysis("AAPL", llm=FakeLLM(content))
    assert result["status"] == "error"
    assert result["sentiment_score"] is None
    assert result["headlines"] == ["Company beats estimates", "Guidance raised"]


def test_valid_model_answer_is_returned():
    with patch("core.research_service.yf.Ticker") as ticker:
        ticker.return_value.news = NEWS
        result = research_service.get_sentiment_analysis("AAPL", llm=FakeLLM('{"score": -0.35, "label": "bearish"}'))
    assert result["status"] == "ok"
    assert result["sentiment_score"] == -0.35
    assert result["sentiment_label"] == "Bearish"
