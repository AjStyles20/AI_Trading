from typing import Any, Dict, List

import pandas as pd


class StrategyValidator:
    def validate(self, strategy_code: str, df: pd.DataFrame) -> Dict[str, Any]:
        warnings: List[str] = []
        local_scope = {"df": df.copy(), "pd": pd}

        try:
            exec(strategy_code, {}, local_scope)
        except Exception as exc:
            return {
                "valid": False,
                "warnings": warnings,
                "errors": [f"Python execution failed: {exc}"],
            }

        try:
            if "strategy" in local_scope:
                result_df = local_scope["strategy"](df.copy())
            else:
                result_df = local_scope.get("df")
        except Exception as exc:
            return {
                "valid": False,
                "warnings": warnings,
                "errors": [f"strategy(df) raised an error: {exc}"],
            }

        if result_df is None:
            return {
                "valid": False,
                "warnings": warnings,
                "errors": ["strategy(df) returned None."],
            }

        if isinstance(result_df, pd.Series):
            if len(result_df) != len(df):
                return {
                    "valid": False,
                    "warnings": warnings,
                    "errors": ["strategy(df) returned a signal series with a different length than the input data."],
                }
            converted = df.copy()
            converted["signal"] = result_df
            result_df = converted

        if not isinstance(result_df, pd.DataFrame):
            return {
                "valid": False,
                "warnings": warnings,
                "errors": ["strategy(df) must return a pandas DataFrame."],
            }

        errors: List[str] = []
        if "close" not in result_df.columns:
            errors.append("Missing required 'close' column.")
        if "signal" not in result_df.columns:
            errors.append("Missing required 'signal' column.")

        if errors:
            return {
                "valid": False,
                "warnings": warnings,
                "errors": errors,
            }

        signal_series = result_df["signal"].fillna(0)
        trade_count = int((signal_series != 0).sum())
        unique_signals = sorted({str(value) for value in signal_series.unique().tolist()})

        if trade_count == 0:
            warnings.append("Strategy produced no actionable buy/sell signals on the selected dataset.")
        if len(result_df) < 20:
            warnings.append("Dataset is very short; backtest metrics may be unreliable.")
        if "position_size_pct" not in result_df.columns:
            warnings.append("Strategy does not define 'position_size_pct'; full-capital entries will be assumed.")

        return {
            "valid": len(errors) == 0,
            "warnings": warnings,
            "errors": errors,
            "stats": {
                "rows": int(len(result_df)),
                "trade_signal_count": trade_count,
                "signal_values": unique_signals,
                "columns": list(result_df.columns),
            },
        }


strategy_validator = StrategyValidator()
