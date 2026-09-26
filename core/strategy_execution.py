from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from core.declarative_strategy import StrategySpec, declarative_strategy_engine
from core.safe_strategy_runtime import safe_strategy_runtime


def execute_strategy_record(strategy: Mapping[str, Any], df: pd.DataFrame) -> pd.DataFrame:
    """Execute a persisted strategy according to its explicit storage format."""
    strategy_format = str(strategy.get("strategy_format") or "legacy_python")

    if strategy_format == "declarative_v1":
        raw_spec = strategy.get("strategy_spec")
        if not isinstance(raw_spec, Mapping) or not raw_spec:
            raise ValueError("declarative_v1 strategy is missing strategy_spec.")
        spec = StrategySpec(
            strategy_type=str(raw_spec.get("strategy_type", "")),
            params=dict(raw_spec.get("params", {})),
            schema_version=int(raw_spec.get("schema_version", 1)),
        )
        return declarative_strategy_engine.execute(spec, df)

    if strategy_format == "legacy_python":
        code = str(strategy.get("code") or "")
        if not code.strip():
            raise ValueError("legacy_python strategy is missing executable code.")
        return safe_strategy_runtime.execute(code, df)

    raise ValueError(f"Unsupported strategy_format: {strategy_format}")
