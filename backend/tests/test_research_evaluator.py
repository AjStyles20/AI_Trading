import pandas as pd
import pytest

from core.research_evaluator import research_evaluator


STRATEGY = """
def strategy(df):
    df = df.copy()
    df['signal'] = 0
    df.iloc[0, df.columns.get_loc('signal')] = 1
    df.iloc[-2, df.columns.get_loc('signal')] = -1
    df['position_size_pct'] = 100
    return df
"""


def frame(rows=100):
    idx = pd.date_range("2026-01-01", periods=rows, freq="h")
    close = [100 + i for i in range(rows)]
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1}, index=idx)


def test_split_is_chronological_and_non_overlapping():
    df = frame()
    split = research_evaluator.split(df)
    assert len(split.train) == 60
    assert len(split.validation) == 20
    assert len(split.test) == 20
    assert split.train.index.max() < split.validation.index.min()
    assert split.validation.index.max() < split.test.index.min()


def test_evaluation_reports_all_holdout_segments():
    result = research_evaluator.evaluate(STRATEGY, frame())
    assert result["rows"] == {"total": 100, "train": 60, "validation": 20, "test": 20}
    assert set(result["segments"]) == {"train", "validation", "test"}
    assert result["selection_policy"].endswith("test is final holdout only")


def test_short_dataset_is_rejected():
    with pytest.raises(ValueError):
        research_evaluator.split(frame(20))
