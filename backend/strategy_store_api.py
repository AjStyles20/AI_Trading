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
    tags: list[str] = Field(default_factory=list)
    builder_graph: Dict[str, Any] = Field(default_factory=dict)
    validation_summary: Dict[str, Any] = Field(default_factory=dict)
    optimization_summary: Dict[str, Any] = Field(default_factory=dict)
    is_baseline: bool = False
    strategy_id: Optional[int] = None


def normalize_strategy_artifact(
    code: str,
    strategy_spec: Dict[str, Any],
    strategy_format: Optional[str],
) -> tuple[str, str, Dict[str, Any]]:
    """Return one unambiguous executable strategy representation."""
    clean_code = code.strip()
    clean_spec = dict(strategy_spec or {})
    inferred_format = strategy_format or ("declarative_v1" if clean_spec else "legacy_python")
    if inferred_format == "declarative_v1":
        if clean_code:
            raise ValueError("declarative_v1 strategies cannot also contain legacy Python code.")
        if not clean_spec:
            raise ValueError("declarative_v1 strategies require strategy_spec.")
        from core.declarative_strategy import StrategySpec
        spec = StrategySpec(
            strategy_type=str(clean_spec.get("strategy_type", "")),
            params=dict(clean_spec.get("params", {})),
            schema_version=int(clean_spec.get("schema_version", 1)),
        )
        canonical_spec = {
            "schema_version": spec.schema_version,
            "strategy_type": spec.strategy_type,
            "params": dict(spec.params),
        }
        return inferred_format, "", canonical_spec
    if inferred_format == "legacy_python":
        if clean_spec:
            raise ValueError("legacy_python strategies cannot also contain strategy_spec.")
        if not clean_code:
            raise ValueError("legacy_python strategies require code.")
        return inferred_format, code, {}
    raise ValueError(f"Unsupported strategy_format: {inferred_format}")


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
        strategy_format, code, strategy_spec = normalize_strategy_artifact(
            request.code,
            request.strategy_spec,
            request.strategy_format,
        )
        strategy_id = save_strategy(
            name=request.name,
            code=code,
            strategy_spec=strategy_spec,
            strategy_format=strategy_format,
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
