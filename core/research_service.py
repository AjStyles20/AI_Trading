import yfinance as yf
from typing import Dict, Any, List
import datetime

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
        """
        Perform a sentiment analysis using LLM based on news headlines.
        """
        ticker = yf.Ticker(symbol)
        news = ticker.news
        headlines = [n.get("title") for n in news[:5]] if news else []
        
        score = 0.5
        label = "Neutral"
        
        if llm and getattr(llm, 'openai_api_key', None) != 'mock-key':
            try:
                import json
                from langchain_core.messages import SystemMessage, HumanMessage
                sys_prompt = "You are a financial sentiment analyzer. Given a list of recent headlines for a stock, calculate an overall sentiment score from -1.0 (extremely negative) to 1.0 (extremely positive). Also provide a label (Bullish, Bearish, or Neutral). Return ONLY a valid JSON with keys 'score' (float) and 'label' (string). No markdown blocks."
                user_prompt = f"Headlines for {symbol}:\n" + "\n".join(headlines)
                resp = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
                parsed = json.loads(resp.content.strip())
                score = float(parsed.get('score', 0))
                label = parsed.get('label', 'Neutral')
            except Exception as e:
                print(f"Sentiment LLM error: {e}")
        
        return {
            "sentiment_score": score,
            "sentiment_label": label,
            "headlines": headlines,
            "timestamp": datetime.datetime.now().isoformat()
        }

    def get_market_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch recent news for a specific symbol."""
        ticker = yf.Ticker(symbol)
        return ticker.news

# Singleton instance
research_service = ResearchService()
