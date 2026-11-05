"""Local backups of the app's database. They stay on this computer."""
from fastapi import APIRouter, HTTPException
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.sqlite_manager import backup_dir, create_backup, list_backups

router = APIRouter()


@router.get("/api/backups")
def get_backups():
    return {"folder": backup_dir(), "items": list_backups()}


@router.post("/api/backups")
def make_backup():
    try:
        return {"folder": backup_dir(), "backup": create_backup()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {type(exc).__name__}") from exc
