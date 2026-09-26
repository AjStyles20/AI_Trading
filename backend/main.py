import sys
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

# Add root folder to sys.path for local imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ai_engine.assistant import ai_assistant
from ai_engine.strategy_generator import StrategyGenerator
from database.sqlite_manager import init_db
from indicators_api import router as indicators_router
from data_api import router as data_router
from research_api import router as research_router
from backtest_api import router as backtest_router
from optimizer_api import router as optimizer_router
from strategy_store_api import router as strategy_store_router
from validation_api import router as validation_router
from settings_api import router as settings_router
from trading_api import router as trading_router

app = FastAPI(
    title="Astral AI Backend",
    description="Backend API for the Astral AI Desktop Application",
    version="1.0.0"
)

# Ensure database is initialized on startup
init_db()

app.add_middleware(
    CORSMiddleware,
    # Desktop development origins only. Wildcard origins combined with credentials
    # unnecessarily expose the local trading API to arbitrary web pages.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(indicators_router)
app.include_router(data_router)
app.include_router(research_router)
app.include_router(backtest_router)
app.include_router(optimizer_router)
app.include_router(strategy_store_router)
app.include_router(validation_router)
app.include_router(settings_router)
app.include_router(trading_router)

class ChatRequest(BaseModel):
    query: str
    conversation_id: str = "default"

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        response = ai_assistant.analyze_market_query(request.query, request.conversation_id)
        return {"response": response, "status": "success"}
    except Exception as e:
        return {"response": f"Error: {str(e)}", "status": "error"}

class StrategyRequest(BaseModel):
    prompt: str

@app.post("/api/strategy")
async def generate_strategy(request: StrategyRequest):
    try:
        generator = StrategyGenerator(ai_assistant.get_llm())
        code = generator.generate(request.prompt)
        return {"code": code, "status": "success"}
    except Exception as e:
        return {"code": "", "error": str(e), "status": "error"}

class BuildRequest(BaseModel):
    nodes: list
    edges: list

@app.post("/api/strategy/build")
async def build_strategy(request: BuildRequest):
    try:
        generator = StrategyGenerator(ai_assistant.llm)
        code = generator.generate_from_graph(request.nodes, request.edges)
        return {"code": code, "status": "success"}
    except Exception as e:
        return {"code": "", "error": str(e), "status": "error"}

class StrategySummaryRequest(BaseModel):
    strategy_code: str
    symbol: str | None = None

@app.post("/api/ai/summary/strategy")
async def summarize_strategy(request: StrategySummaryRequest):
    try:
        summary = ai_assistant.summarize_strategy(request.strategy_code, request.symbol)
        return {"summary": summary, "status": "success"}
    except Exception as e:
        return {"summary": "", "error": str(e), "status": "error"}

class BacktestSummaryRequest(BaseModel):
    backtest_results: dict
    symbol: str | None = None

@app.post("/api/ai/summary/backtest")
async def summarize_backtest(request: BacktestSummaryRequest):
    try:
        summary = ai_assistant.summarize_backtest(request.backtest_results, request.symbol)
        return {"summary": summary, "status": "success"}
    except Exception as e:
        return {"summary": "", "error": str(e), "status": "error"}

@app.get("/")
def read_root():
    return {"message": "Welcome to Astral AI Trading Backend"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
