from fastapi import APIRouter, HTTPException
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.research_service import research_service
from ai_engine.assistant import ai_assistant

router = APIRouter()

@router.get("/api/research/info/{symbol}")
def get_info(symbol: str):
    try:
        return research_service.get_company_info(symbol)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/research/sentiment/{symbol}")
def get_sentiment(symbol: str):
    try:
        return research_service.get_sentiment_analysis(symbol, llm=ai_assistant.llm)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/research/news/{symbol}")
def get_news(symbol: str):
    try:
        return research_service.get_market_news(symbol)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
