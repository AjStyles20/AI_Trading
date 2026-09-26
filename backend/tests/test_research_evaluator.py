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


def test_walk_forward_uses_ordered_non_overlapping_train_test_boundaries():
    df = frame(80)
    result = research_evaluator.walk_forward(STRATEGY, df, train_rows=40, test_rows=10, step_rows=10)
    assert result["window_count"] == 4
    assert result["method"] == "rolling_out_of_sample_fixed_strategy"
    assert result["legacy_method_alias"] == "walk_forward"
    assert "fixed before evaluation" in result["selection_policy"]
    assert "positive_test_windows" in result["summary"]
    for window in result["windows"]:
        assert pd.Timestamp(window["train_end"]) < pd.Timestamp(window["test_start"])


def test_walk_forward_rejects_insufficient_history():
    with pytest.raises(ValueError):
        research_evaluator.walk_forward(STRATEGY, frame(30), train_rows=25, test_rows=10)


def test_named_rolling_oos_api_does_not_claim_parameter_reselection():
    result = research_evaluator.rolling_out_of_sample(
        STRATEGY, frame(80), train_rows=40, test_rows=10, step_rows=10
    )
    assert result["method"] == "rolling_out_of_sample_fixed_strategy"
    assert "re-selection" in result["selection_policy"]
    assert "legacy_method_alias" not in result
