"""Price alerts: stored here, checked by the desktop app while it is open."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.sqlite_manager import (
    create_price_alert,
    delete_price_alert,
    get_price_alert,
    get_price_alerts,
    trigger_price_alert,
)

router = APIRouter()

MAX_ACTIVE_ALERTS = 100


class AlertRequest(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9^][A-Za-z0-9.=^/-]{0,19}$")
    asset_type: Literal["crypto", "stock"]
    direction: Literal["above", "below"]
    price: float = Field(gt=0, allow_inf_nan=False)
    note: str = Field(default="", max_length=200)


class TriggerRequest(BaseModel):
    price: float = Field(gt=0, allow_inf_nan=False)


@router.get("/api/alerts")
def list_alerts():
    return {"items": get_price_alerts()}


@router.post("/api/alerts")
def add_alert(request: AlertRequest):
    active = sum(1 for alert in get_price_alerts() if alert["triggered_at"] is None)
    if active >= MAX_ACTIVE_ALERTS:
        raise HTTPException(status_code=400, detail=f"You can have up to {MAX_ACTIVE_ALERTS} active alerts. Delete one first.")
    return create_price_alert(
        request.symbol.strip().upper(), request.asset_type, request.direction, request.price, request.note.strip()
    )


@router.post("/api/alerts/{alert_id}/trigger")
def mark_triggered(alert_id: int, request: TriggerRequest):
    alert = get_price_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    # The app reports a crossing; confirm it before recording, so a stale or
    # wrong price can't mark an alert as hit.
    crossed = request.price >= alert["price"] if alert["direction"] == "above" else request.price <= alert["price"]
    if not crossed:
        raise HTTPException(status_code=400, detail="That price does not reach the alert level.")
    return trigger_price_alert(alert_id, request.price)


@router.delete("/api/alerts/{alert_id}")
def remove_alert(alert_id: int):
    if not delete_price_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"status": "deleted"}
