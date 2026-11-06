import yfinance as yf
from typing import Dict, Any, List
import datetime
import math

SENTIMENT_LABELS = {"Bullish", "Bearish", "Neutral"}

class ResearchService:
    def __init__(self):
        pass

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data for a stock."""
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "name": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "dividend_yield": info.get("dividendYield"),
            "summary": info.get("longBusinessSummary")
        }

    def get_sentiment_analysis(self, symbol: str, llm=None) -> Dict[str, Any]:
        """Score recent headlines with the configured LLM.

        Without a provider, headlines or a valid model answer there is no
        score: the result says why instead of inventing a neutral number.
        """
        def result(status: str, score=None, label=None, headlines=None, reason=None) -> Dict[str, Any]:
            return {
                "status": status,
                "sentiment_score": score,
                "sentiment_label": label,
                "reason": reason,
                "headlines": headlines or [],
                "timestamp": datetime.datetime.now().isoformat(),
            }

        if llm is None:
            return result("needs_ai", reason="No AI provider is configured. Choose one in Settings to score news sentiment.")

        news = yf.Ticker(symbol).news
        headlines = [n.get("title") for n in news[:5] if n.get("title")] if news else []
        if not headlines:
            return result("unavailable", reason=f"No recent headlines were found for {symbol}.")

        try:
            import json
            from langchain_core.messages import SystemMessage, HumanMessage
            sys_prompt = "You are a financial sentiment analyzer. Given a list of recent headlines for a stock, calculate an overall sentiment score from -1.0 (extremely negative) to 1.0 (extremely positive). Also provide a label (Bullish, Bearish, or Neutral). Return ONLY a valid JSON with keys 'score' (float) and 'label' (string). No markdown blocks."
            user_prompt = f"Headlines for {symbol}:\n" + "\n".join(headlines)
            resp = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
            parsed = json.loads(resp.content.strip())
            score = float(parsed["score"])
            label = str(parsed["label"]).strip().title()
            if not math.isfinite(score) or not -1.0 <= score <= 1.0 or label not in SENTIMENT_LABELS:
                raise ValueError(f"model returned score={parsed.get('score')!r}, label={parsed.get('label')!r}")
        except Exception as e:
            print(f"Sentiment LLM error: {e}")
            return result("error", headlines=headlines, reason="The AI provider did not return a usable sentiment score.")
        return result("ok", score=score, label=label, headlines=headlines)

    def get_market_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch recent news for a specific symbol."""
        ticker = yf.Ticker(symbol)
        return ticker.news

# Singleton instance
research_service = ResearchService()
