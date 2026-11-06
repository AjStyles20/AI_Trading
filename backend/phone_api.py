"""Pairing phones with the read-only phone gateway (desktop side, loopback only)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import ipaddress
import json
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

GATEWAY_CONFIG_NAME = "phone_gateway.json"


def gateway_config_path() -> str:
    # Read by the desktop app at launch to decide whether to start the gateway.
    from database import sqlite_manager
    return os.path.join(os.path.dirname(sqlite_manager.DB_PATH), GATEWAY_CONFIG_NAME)


class GatewayConfig(BaseModel):
    # A Tailscale address turns phone access on at the next launch; null turns it off.
    host: Optional[str] = None


class PairRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r"^[\w .'-]+$")


def _audit(action: str, details: dict) -> None:
    try:
        record_audit_event("phone", action, details)
    except Exception as exc:
        print(f"WARNING: Failed to record phone audit event: {type(exc).__name__}")


@router.get("/api/phone/gateway")
def get_gateway_config():
    try:
        with open(gateway_config_path(), encoding="utf-8") as handle:
            host = json.load(handle).get("host")
    except (OSError, ValueError):
        host = None
    return {"host": host if isinstance(host, str) else None}


@router.put("/api/phone/gateway")
def set_gateway_config(config: GatewayConfig):
    host = (config.host or "").strip() or None
    if host is not None:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        # Only a Tailscale address: the packaged app never starts the gateway on loopback
        # or any other network.
        if address is None or address.version != 4 or address not in ipaddress.ip_network("100.64.0.0/10"):
            raise HTTPException(status_code=400, detail="Use this computer's Tailscale address (100.64.0.0 to 100.127.255.255).")
    path = gateway_config_path()
    if host is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    else:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"host": host}, handle)
    _audit("gateway_enabled" if host else "gateway_disabled", {"host": host})
    return {"host": host}


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
