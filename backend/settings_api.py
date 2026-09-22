from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.sqlite_manager import get_settings, update_settings

router = APIRouter()

class SettingsUpdate(BaseModel):
    api_keys: Optional[Dict[str, str]] = None
    theme: Optional[str] = None
    paper_trading: Optional[bool] = None

@router.get("/api/settings")
def get_current_settings():
    settings = get_settings()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    return settings

@router.post("/api/settings")
def save_settings(update: SettingsUpdate):
    try:
        success = update_settings(
            api_keys=update.api_keys,
            theme=update.theme,
            paper_trading=update.paper_trading
        )
        if success:
            # Trigger AI Assistant reload if API keys changed
            from ai_engine.assistant import ai_assistant
            ai_assistant.reload_settings()
            return {"status": "success", "message": "Settings updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update settings")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
