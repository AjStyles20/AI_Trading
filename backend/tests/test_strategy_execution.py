import pandas as pd
import pytest

from core.strategy_execution import execute_strategy_record


def frame():
    return pd.DataFrame({"close": [100.0, 101.0, 103.0, 102.0, 105.0]})


def test_executes_declarative_record_without_python_code():
    record = {
        "strategy_format": "declarative_v1",
        "code": "",
        "strategy_spec": {
            "schema_version": 1,
            "strategy_type": "sma_cross",
            "params": {
                "sma_fast": 2, "sma_slow": 3,
                "position_size_pct": 50,
                "stop_loss_pct": 2, "take_profit_pct": 4,
            },
        },
    }
    result = execute_strategy_record(record, frame())
    assert "signal" in result.columns
    assert (result["position_size_pct"] == 50).all()


def test_executes_legacy_record_through_compatibility_runtime():
    record = {
        "strategy_format": "legacy_python",
        "code": "def strategy(df):\n    df = df.copy()\n    df['signal'] = 0\n    return df",
        "strategy_spec": {},
    }
    result = execute_strategy_record(record, frame())
    assert "signal" in result.columns


def test_declarative_record_does_not_fall_back_to_python():
    record = {
        "strategy_format": "declarative_v1",
        "code": "def strategy(df):\n    raise RuntimeError('must not execute')",
        "strategy_spec": {},
    }
    with pytest.raises(ValueError, match="missing strategy_spec"):
        execute_strategy_record(record, frame())


def test_unknown_strategy_format_fails_closed():
    with pytest.raises(ValueError, match="Unsupported strategy_format"):
        execute_strategy_record({"strategy_format": "future_v9"}, frame())
