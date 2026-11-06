"""Pairing phones with the read-only phone gateway (desktop side, loopback only)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.sqlite_manager import (
    create_phone_device,
    list_phone_devices,
    record_audit_event,
    revoke_phone_device,
)

router = APIRouter()


class PairRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r"^[\w .'-]+$")


def _audit(action: str, details: dict) -> None:
    try:
        record_audit_event("phone", action, details)
    except Exception as exc:
        print(f"WARNING: Failed to record phone audit event: {type(exc).__name__}")


@router.get("/api/phone/devices")
def get_devices():
    return {"items": list_phone_devices()}


@router.post("/api/phone/devices")
def pair_device(request: PairRequest):
    device = create_phone_device(request.name.strip())
    _audit("paired", {"device_id": device["id"], "name": device["name"]})
    # The token is returned this once and never stored in plain form.
    return device


@router.delete("/api/phone/devices/{device_id}")
def revoke_device(device_id: int):
    if not revoke_phone_device(device_id):
        raise HTTPException(status_code=404, detail="No active device with that id.")
    _audit("revoked", {"device_id": device_id})
    return {"status": "revoked"}
