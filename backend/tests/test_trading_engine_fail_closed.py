import pandas as pd
import pytest

from core.trading_engine import TradingEngine


def sample_frame():
    return pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [10.0]}
    )


def test_strategy_execution_error_propagates():
    code = """
def strategy(df):
    return 1 / 0
"""
    with pytest.raises(ZeroDivisionError):
        TradingEngine().evaluate_strategy(code, sample_frame())


def test_strategy_must_return_dataframe():
    code = """
def strategy(df):
    return 123
"""
    with pytest.raises(ValueError, match="must return a pandas DataFrame or signal Series"):
        TradingEngine().evaluate_strategy(code, sample_frame())


def test_empty_strategy_result_is_rejected():
    code = """
def strategy(df):
    return df.iloc[0:0]
"""
    with pytest.raises(ValueError, match="empty DataFrame"):
        TradingEngine().evaluate_strategy(code, sample_frame())
