from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd

from core.backtest_engine import backtest_engine
from core.safe_strategy_runtime import safe_strategy_runtime


@dataclass(frozen=True)
class ChronologicalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    train_end: int
    validation_end: int


class ResearchEvaluator:
    """Chronological research evaluation. The final test segment is never used for selection."""

    def split(self, df: pd.DataFrame, train_ratio: float = 0.6, validation_ratio: float = 0.2) -> ChronologicalSplit:
        if not 0 < train_ratio < 1 or not 0 < validation_ratio < 1:
            raise ValueError("Split ratios must be between 0 and 1.")
        if train_ratio + validation_ratio >= 1:
            raise ValueError("Train + validation ratios must leave a non-empty test segment.")
        if len(df) < 30:
            raise ValueError("At least 30 chronological rows are required for research evaluation.")
        train_end = int(len(df) * train_ratio)
        validation_end = int(len(df) * (train_ratio + validation_ratio))
        if train_end < 1 or validation_end <= train_end or validation_end >= len(df):
            raise ValueError("Dataset is too small for the requested chronological split.")
        return ChronologicalSplit(
            train=df.iloc[:train_end].copy(),
            validation=df.iloc[train_end:validation_end].copy(),
            test=df.iloc[validation_end:].copy(),
            train_end=train_end,
            validation_end=validation_end,
        )

    def evaluate(
        self,
        strategy_code: str,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.05,
        train_ratio: float = 0.6,
        validation_ratio: float = 0.2,
    ) -> Dict[str, Any]:
        split = self.split(df, train_ratio, validation_ratio)
        output: Dict[str, Any] = {
            "method": "chronological_holdout",
            "selection_policy": "train/validation may be used for development; test is final holdout only",
            "rows": {
                "total": len(df),
                "train": len(split.train),
                "validation": len(split.validation),
                "test": len(split.test),
            },
            "segments": {},
        }
        for name, segment in (
            ("train", split.train),
            ("validation", split.validation),
            ("test", split.test),
        ):
            strategy_df = safe_strategy_runtime.execute(strategy_code, segment)
            metrics = backtest_engine.run_backtest(
                strategy_df,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            output["segments"][name] = metrics
        return output


research_evaluator = ResearchEvaluator()
