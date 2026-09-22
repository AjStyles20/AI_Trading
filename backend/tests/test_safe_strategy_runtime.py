import pandas as pd
import pytest

from core.safe_strategy_runtime import SafeStrategyRuntime, UnsafeStrategyError


@pytest.fixture
def frame():
    return pd.DataFrame({"close": [100.0, 101.0, 102.0]})


def test_valid_strategy_executes(frame):
    code = """
def strategy(df):
    df = df.copy()
    df['signal'] = 0
    df.loc[df['close'] > 100, 'signal'] = 1
    return df
"""
    result = SafeStrategyRuntime().execute(code, frame)
    assert result["signal"].tolist() == [0, 1, 1]


@pytest.mark.parametrize("code", [
    "import os\ndef strategy(df):\n    return df",
    "def strategy(df):\n    open('x.txt', 'w')\n    return df",
    "def strategy(df):\n    return df.__class__",
    "def strategy(df):\n    return pd.read_csv('secret.csv')",
])
def test_unsafe_operations_are_rejected(frame, code):
    with pytest.raises(UnsafeStrategyError):
        SafeStrategyRuntime().execute(code, frame)


def test_requires_single_strategy_function(frame):
    with pytest.raises(UnsafeStrategyError):
        SafeStrategyRuntime().execute("x = 1", frame)
