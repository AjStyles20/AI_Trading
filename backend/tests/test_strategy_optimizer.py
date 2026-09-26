import pandas as pd

from core.strategy_optimizer import strategy_optimizer


def frame(rows=60):
    idx = pd.date_range("2026-01-01", periods=rows, freq="h")
    close = [100 + (i % 10) for i in range(rows)]
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1}, index=idx)


def test_optimizer_reserves_final_holdout():
    result = strategy_optimizer.optimize(
        frame(),
        strategy_type="sma_cross",
        custom_ranges={
            "sma_fast": [2],
            "sma_slow": [4],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    assert result["method"] == "chronological_development_holdout"
    assert result["selection_rows"] == 48
    assert result["holdout_rows"] == 12
    assert result["best"] is not None
    assert result["holdout"] is not None
    assert result["holdout"]["params"] == result["best"]["params"]


def test_walk_forward_optimizer_selects_before_each_unseen_window():
    result = strategy_optimizer.walk_forward_optimize(
        frame(80),
        strategy_type="sma_cross",
        train_rows=30,
        test_rows=10,
        step_rows=10,
        custom_ranges={
            "sma_fast": [2],
            "sma_slow": [4],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    assert result["method"] == "rolling_walk_forward_parameter_selection"
    assert result["window_count"] == 5
    assert "training window only" in result["selection_policy"]
    for window in result["windows"]:
        assert pd.Timestamp(window["train_end"]) < pd.Timestamp(window["test_start"])
        assert window["selected_params"]["sma_fast"] == 2
        assert "test_metrics" in window


def test_walk_forward_optimizer_rejects_overlapping_oos_windows():
    import pytest

    with pytest.raises(ValueError, match="prevent overlapping OOS"):
        strategy_optimizer.walk_forward_optimize(
            frame(80),
            strategy_type="sma_cross",
            train_rows=30,
            test_rows=10,
            step_rows=5,
            custom_ranges={
                "sma_fast": [2],
                "sma_slow": [4],
                "stop_loss_pct": [2],
                "take_profit_pct": [4],
                "cooldown_bars": [0],
                "position_size_pct": [50],
            },
        )


def test_walk_forward_warmup_uses_only_pre_test_context():
    df = frame(80)
    result = strategy_optimizer.walk_forward_optimize(
        df,
        strategy_type="sma_cross",
        train_rows=30,
        test_rows=10,
        step_rows=10,
        warmup_rows=4,
        custom_ranges={
            "sma_fast": [2],
            "sma_slow": [4],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    assert result["warmup_rows"] == 4
    assert "never participate in parameter selection" in result["warmup_policy"]
    for window in result["windows"]:
        for trade in window["test_metrics"]["trade_history"]:
            assert pd.Timestamp(trade["timestamp"]) >= pd.Timestamp(window["test_start"])
