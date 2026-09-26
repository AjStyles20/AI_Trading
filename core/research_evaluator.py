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
        warmup_rows: int = 0,
    ) -> Dict[str, Any]:
        if warmup_rows < 0:
            raise ValueError("warmup_rows must be non-negative.")
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
            "warmup_rows": warmup_rows,
            "warmup_policy": "past-only context is used to initialize indicators; metrics and trades are restricted to the evaluated segment",
        }
        segment_specs = (
            ("train", split.train, 0),
            ("validation", split.validation, split.train_end),
            ("test", split.test, split.validation_end),
        )
        for name, segment, start_position in segment_specs:
            if warmup_rows and start_position > 0:
                context_start = max(0, start_position - warmup_rows)
                context = df.iloc[context_start:start_position + len(segment)].copy()
                strategy_with_context = safe_strategy_runtime.execute(strategy_code, context)
                strategy_df = strategy_with_context.iloc[-len(segment):].copy()
            else:
                strategy_df = safe_strategy_runtime.execute(strategy_code, segment)
            metrics = backtest_engine.run_backtest(
                strategy_df,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            output["segments"][name] = metrics
        return output
    def rolling_out_of_sample(
        self,
        strategy_code: str,
        df: pd.DataFrame,
        train_rows: int,
        test_rows: int,
        step_rows: int | None = None,
        initial_balance: float = 10000.0,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.05,
        warmup_rows: int = 0,
    ) -> Dict[str, Any]:
        if warmup_rows < 0:
            raise ValueError("warmup_rows must be non-negative.")
        if train_rows < 20 or test_rows < 5:
            raise ValueError("Walk-forward requires train_rows >= 20 and test_rows >= 5.")
        step = step_rows or test_rows
        if step < 1:
            raise ValueError("step_rows must be positive.")
        if len(df) < train_rows + test_rows:
            raise ValueError("Dataset is too short for one complete walk-forward window.")

        windows = []
        start = 0
        window_id = 1
        while start + train_rows + test_rows <= len(df):
            train = df.iloc[start:start + train_rows].copy()
            test_start = start + train_rows
            test = df.iloc[test_start:test_start + test_rows].copy()
            if warmup_rows:
                context_start = max(0, test_start - warmup_rows)
                context = df.iloc[context_start:test_start + test_rows].copy()
                test_with_context = safe_strategy_runtime.execute(strategy_code, context)
                test_signals = test_with_context.iloc[-test_rows:].copy()
            else:
                test_signals = safe_strategy_runtime.execute(strategy_code, test)
            metrics = backtest_engine.run_backtest(
                test_signals,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            windows.append({
                "window": window_id,
                "train_start": str(train.index[0]),
                "train_end": str(train.index[-1]),
                "test_start": str(test.index[0]),
                "test_end": str(test.index[-1]),
                "test_metrics": metrics,
            })
            window_id += 1
            start += step

        returns = [window["test_metrics"]["total_return_pct"] for window in windows]
        drawdowns = [window["test_metrics"]["max_drawdown_pct"] for window in windows]
        return {
            "method": "rolling_out_of_sample_fixed_strategy",
            "selection_policy": "strategy is fixed before evaluation; train windows are context only and are not used for re-selection",
            "train_rows": train_rows,
            "test_rows": test_rows,
            "step_rows": step,
            "warmup_rows": warmup_rows,
            "warmup_policy": "past-only context initializes indicators; only OOS rows are backtested",
            "window_count": len(windows),
            "summary": {
                "mean_test_return_pct": round(sum(returns) / len(returns), 4),
                "positive_test_windows": sum(value > 0 for value in returns),
                "worst_test_drawdown_pct": round(min(drawdowns), 4),
            },
            "windows": windows,
        }

    def walk_forward(
        self,
        strategy_code: str,
        df: pd.DataFrame,
        train_rows: int,
        test_rows: int,
        step_rows: int | None = None,
        initial_balance: float = 10000.0,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.05,
    ) -> Dict[str, Any]:
        """Backward-compatible alias for fixed-strategy rolling OOS evaluation.

        This is not parameter re-selection walk-forward optimization.
        """
        result = self.rolling_out_of_sample(
            strategy_code=strategy_code,
            df=df,
            train_rows=train_rows,
            test_rows=test_rows,
            step_rows=step_rows,
            initial_balance=initial_balance,
            fee_pct=fee_pct,
            slippage_pct=slippage_pct,
        )
        result["legacy_method_alias"] = "walk_forward"
        return result


research_evaluator = ResearchEvaluator()
