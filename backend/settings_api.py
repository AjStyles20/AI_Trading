from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Optional
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.sqlite_manager import get_audit_events, get_public_settings, get_settings, record_audit_event, update_settings, remove_legacy_api_keys
from core.credential_provider import credential_presence, set_secure_credential, migrate_legacy_credentials

router = APIRouter()


def _audit_settings_change(before: dict, update: "SettingsUpdate") -> None:
    """Record what a save changed. Credentials are recorded by name only, never by value."""
    requested = update.model_dump(exclude={"api_keys"}, exclude_none=True)
    changes = {
        field: {"from": before.get(field), "to": value}
        for field, value in requested.items()
        if before.get(field) != value
    }
    credentials = {
        name: "set" if value else "cleared"
        for name, value in (update.api_keys or {}).items()
        if value != "********"
    }
    if not changes and not credentials:
        return
    details = {"changes": changes}
    if credentials:
        details["credentials"] = credentials
    # A logging problem must never block a save such as arming the kill switch.
    try:
        record_audit_event("settings", "updated", details)
    except Exception as e:
        print(f"WARNING: Failed to record settings audit event: {type(e).__name__}")


@router.get("/api/audit")
def list_audit_events(limit: int = Query(100, ge=1, le=500)):
    return {"items": get_audit_events(limit)}


class SettingsUpdate(BaseModel):
    api_keys: Optional[Dict[str, str]] = None
    theme: Optional[str] = None
    paper_trading: Optional[bool] = None
    risk_live_trading_enabled: Optional[bool] = None
    autonomy_kill_switch: Optional[bool] = None
    risk_max_order_notional: Optional[float] = None
    risk_max_position_pct: Optional[float] = None
    risk_max_daily_loss_pct: Optional[float] = None
    risk_max_drawdown_pct: Optional[float] = None
    binance_environment: Optional[str] = None
    bitget_environment: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    ai_vision_model: Optional[str] = None
    bitget_account_type: Optional[str] = None

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
        before = get_public_settings() or {}
        secure_updates = update.api_keys or {}
        for key, value in secure_updates.items():
            if value != "********":
                set_secure_credential(key, value)

        success = update_settings(
            api_keys={key: ("********" if value else "") for key, value in secure_updates.items()} if update.api_keys is not None else None,
            theme=update.theme,
            paper_trading=update.paper_trading,
            risk_live_trading_enabled=update.risk_live_trading_enabled,
            autonomy_kill_switch=update.autonomy_kill_switch,
            risk_max_order_notional=update.risk_max_order_notional,
            risk_max_position_pct=update.risk_max_position_pct,
            risk_max_daily_loss_pct=update.risk_max_daily_loss_pct,
            risk_max_drawdown_pct=update.risk_max_drawdown_pct,
            binance_environment=update.binance_environment,
            bitget_environment=update.bitget_environment,
            ai_provider=update.ai_provider,
            ai_model=update.ai_model,
            ai_vision_model=update.ai_vision_model,
            bitget_account_type=update.bitget_account_type,
        )
        if success:
            _audit_settings_change(before, update)
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
