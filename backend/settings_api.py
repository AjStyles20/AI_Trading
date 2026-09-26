from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.sqlite_manager import get_public_settings, get_settings, update_settings, remove_legacy_api_keys
from core.credential_provider import credential_presence, set_secure_credential, migrate_legacy_credentials

router = APIRouter()

class SettingsUpdate(BaseModel):
    api_keys: Optional[Dict[str, str]] = None
    theme: Optional[str] = None
    paper_trading: Optional[bool] = None
    risk_live_trading_enabled: Optional[bool] = None
    risk_max_order_notional: Optional[float] = None
    risk_max_position_pct: Optional[float] = None
    risk_max_daily_loss_pct: Optional[float] = None
    risk_max_drawdown_pct: Optional[float] = None
    binance_environment: Optional[str] = None
    bitget_environment: Optional[str] = None

@router.get("/api/settings")
def get_current_settings():
    settings = get_public_settings()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    internal = get_settings() or {}
    settings["credential_presence"] = credential_presence(internal)
    return settings

@router.post("/api/settings/migrate-credentials")
def migrate_credentials():
    """Explicitly migrate verified legacy SQLite secrets into the OS keyring."""
    try:
        internal = get_settings() or {}
        migrated = migrate_legacy_credentials(internal)
        if migrated and not remove_legacy_api_keys(migrated):
            raise HTTPException(
                status_code=500,
                detail="Credentials were secured but legacy cleanup failed.",
            )
        return {
            "status": "success",
            "migrated": migrated,
            "migrated_count": len(migrated),
        }
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Credential migration failed") from e


@router.post("/api/settings")
def save_settings(update: SettingsUpdate):
    try:
        secure_updates = update.api_keys or {}
        for key, value in secure_updates.items():
            if value != "********":
                set_secure_credential(key, value)

        success = update_settings(
            api_keys={key: ("********" if value else "") for key, value in secure_updates.items()} if update.api_keys is not None else None,
            theme=update.theme,
            paper_trading=update.paper_trading,
            risk_live_trading_enabled=update.risk_live_trading_enabled,
            risk_max_order_notional=update.risk_max_order_notional,
            risk_max_position_pct=update.risk_max_position_pct,
            risk_max_daily_loss_pct=update.risk_max_daily_loss_pct,
            risk_max_drawdown_pct=update.risk_max_drawdown_pct,
            binance_environment=update.binance_environment,
            bitget_environment=update.bitget_environment
        )
        if success:
            # Trigger AI Assistant reload if API keys changed
            from ai_engine.assistant import ai_assistant
            ai_assistant.reload_settings()
            return {"status": "success", "message": "Settings updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update settings")
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update settings") from e
