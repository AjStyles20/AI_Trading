from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.sqlite_manager import (
    archive_strategies,
    archive_strategy,
    duplicate_strategy,
    get_strategies,
    get_strategy,
    permanently_delete_archived_strategies,
    restore_strategies,
    restore_strategy,
    save_strategy,
    set_strategy_baseline,
)

router = APIRouter()


class StrategySaveRequest(BaseModel):
    name: str
    code: str = ""
    strategy_spec: Dict[str, Any] = Field(default_factory=dict)
    strategy_format: Optional[str] = None
    symbol: str = ""
    asset_type: str = "crypto"
    tags: list[str] = []
    builder_graph: Dict[str, Any] = {}
    validation_summary: Dict[str, Any] = {}
    optimization_summary: Dict[str, Any] = {}
    is_baseline: bool = False
    strategy_id: Optional[int] = None


class StrategyBulkActionRequest(BaseModel):
    strategy_ids: list[int]


@router.get("/api/strategies")
def list_strategies(
    include_archived: bool = Query(False),
    archived_only: bool = Query(False),
):
    return {"items": get_strategies(include_archived=include_archived, archived_only=archived_only)}


@router.get("/api/strategies/{strategy_id}")
def fetch_strategy(strategy_id: int):
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.post("/api/strategies")
def store_strategy(request: StrategySaveRequest):
    try:
        if not request.code.strip() and not request.strategy_spec:
            raise ValueError("A strategy must provide either legacy Python code or a declarative strategy_spec.")
        if request.strategy_spec:
            from core.declarative_strategy import StrategySpec
            StrategySpec(
                strategy_type=str(request.strategy_spec.get("strategy_type", "")),
                params=dict(request.strategy_spec.get("params", {})),
                schema_version=int(request.strategy_spec.get("schema_version", 1)),
            )
        strategy_id = save_strategy(
            name=request.name,
            code=request.code,
            strategy_spec=request.strategy_spec,
            strategy_format=request.strategy_format,
            symbol=request.symbol,
            asset_type=request.asset_type,
            tags=request.tags,
            builder_graph=request.builder_graph,
            validation_summary=request.validation_summary,
            optimization_summary=request.optimization_summary,
            is_baseline=request.is_baseline,
            strategy_id=request.strategy_id,
        )
        return {
            "status": "success",
            "strategy_id": strategy_id,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/strategies/{strategy_id}/duplicate")
def clone_strategy(strategy_id: int):
    duplicated_id = duplicate_strategy(strategy_id)
    if not duplicated_id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "success", "strategy_id": duplicated_id}


@router.post("/api/strategies/{strategy_id}/baseline")
def mark_strategy_baseline(strategy_id: int):
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    set_strategy_baseline(strategy_id)
    return {"status": "success"}


@router.delete("/api/strategies/{strategy_id}")
def delete_strategy(strategy_id: int):
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    archive_strategy(strategy_id)
    return {"status": "success"}


@router.post("/api/strategies/{strategy_id}/restore")
def unarchive_strategy(strategy_id: int):
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    restore_strategy(strategy_id)
    return {"status": "success"}


@router.post("/api/strategies/bulk/archive")
def bulk_archive(request: StrategyBulkActionRequest):
    if not request.strategy_ids:
        raise HTTPException(status_code=400, detail="No strategy ids provided")
    affected = archive_strategies(request.strategy_ids)
    return {"status": "success", "affected": affected}


@router.post("/api/strategies/bulk/restore")
def bulk_restore(request: StrategyBulkActionRequest):
    if not request.strategy_ids:
        raise HTTPException(status_code=400, detail="No strategy ids provided")
    affected = restore_strategies(request.strategy_ids)
    return {"status": "success", "affected": affected}


@router.post("/api/strategies/bulk/delete")
def bulk_delete_archived(request: StrategyBulkActionRequest):
    if not request.strategy_ids:
        raise HTTPException(status_code=400, detail="No strategy ids provided")
    affected = permanently_delete_archived_strategies(request.strategy_ids)
    return {"status": "success", "affected": affected}
