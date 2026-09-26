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


def test_optimizer_reports_evidence_adjusted_score():
    result = strategy_optimizer.optimize(
        frame(60),
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
    candidate = result["best"]
    assert "raw_score" in candidate
    assert "evidence_factor" in candidate
    assert "closed_round_trips" in candidate
    assert 0 <= candidate["evidence_factor"] <= 1
    assert candidate["score"] == round(candidate["raw_score"] * candidate["evidence_factor"], 3)


def test_candidate_score_does_not_use_buy_hold_return(monkeypatch):
    class FakeBacktest:
        def __init__(self):
            self.buy_hold = 999999.0

        def run_backtest(self, *args, **kwargs):
            return {
                "total_return_pct": 10.0,
                "win_rate_pct": 50.0,
                "buy_hold_return_pct": self.buy_hold,
                "max_drawdown_pct": -5.0,
                "trade_count": 10,
                "closed_round_trips": 5,
                "profit_factor": 1.5,
                "final_equity": 11000.0,
            }

    fake = FakeBacktest()
    monkeypatch.setattr("core.strategy_optimizer.backtest_engine", fake)
    result = strategy_optimizer.optimize(
        frame(60),
        strategy_type="sma_cross",
        custom_ranges={
            "sma_fast": [2],
            "sma_slow": [4],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
    )
    score_before = result["best"]["score"]
    fake.buy_hold = -999999.0
    result_after = strategy_optimizer.optimize(
        frame(60),
        strategy_type="sma_cross",
        custom_ranges={
            "sma_fast": [2],
            "sma_slow": [4],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
    )
    assert result_after["best"]["score"] == score_before


def test_optimizer_reports_search_space_risk():
    result = strategy_optimizer.optimize(
        frame(60),
        strategy_type="sma_cross",
        custom_ranges={
            "sma_fast": [2, 3],
            "sma_slow": [4, 5],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    risk = result["optimization_risk"]
    # Explicit zero cooldown is a real candidate, not a request for defaults.
    # 2 fast x 2 slow x 1 cooldown = 4 valid candidates.
    assert risk["candidate_count"] == 4
    assert risk["development_rows"] == 48
    assert risk["observations_per_candidate"] == 4.0
    assert any("Fewer than five development observations" in warning for warning in risk["warnings"])
    assert risk["winner_closed_round_trips"] == result["best"]["closed_round_trips"]
    assert isinstance(risk["warnings"], list)
    assert "not statistical significance tests" in risk["interpretation"]


def test_optimizer_warns_when_candidates_exceed_development_rows():
    result = strategy_optimizer.optimize(
        frame(30),
        strategy_type="sma_cross",
        custom_ranges={
            "sma_fast": list(range(1, 7)),
            "sma_slow": list(range(7, 13)),
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    risk = result["optimization_risk"]
    assert risk["candidate_count"] > risk["development_rows"]
    assert any("multiple-testing overfit" in warning for warning in risk["warnings"])


def test_walk_forward_exposes_selection_risk_per_window():
    result = strategy_optimizer.walk_forward_optimize(
        frame(80),
        strategy_type="sma_cross",
        train_rows=30,
        test_rows=10,
        step_rows=10,
        custom_ranges={
            "sma_fast": [2, 3],
            "sma_slow": [4, 5],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [0],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    assert result["window_count"] == 5
    assert result["summary"]["weak_selection_windows"] >= 1
    assert result["summary"]["total_selection_warnings"] >= result["summary"]["weak_selection_windows"]
    for window in result["windows"]:
        assert "selection_risk" in window
        assert "candidate_count" in window["selection_risk"]
        assert "selection_evidence_factor" in window
        assert "selection_raw_score" in window


def test_optimizer_exposes_canonical_declarative_strategy_spec():
    result = strategy_optimizer.optimize(
        frame(60),
        strategy_type="sma_cross",
        custom_ranges={
            "sma_fast": [2],
            "sma_slow": [4],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [1],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    best = result["best"]
    assert best["strategy_spec"]["schema_version"] == 1
    assert best["strategy_spec"]["strategy_type"] == "sma_cross"
    assert best["strategy_spec"]["params"] == best["params"]
    assert best["code_status"] == "legacy_compatibility_only"
    assert "strategy_spec is canonical" in result["artifact_policy"]


def test_walk_forward_records_selected_strategy_spec():
    result = strategy_optimizer.walk_forward_optimize(
        frame(60),
        strategy_type="sma_cross",
        train_rows=30,
        test_rows=10,
        step_rows=10,
        custom_ranges={
            "sma_fast": [2],
            "sma_slow": [4],
            "stop_loss_pct": [2],
            "take_profit_pct": [4],
            "cooldown_bars": [1],
            "position_size_pct": [50],
        },
        fee_pct=0,
        slippage_pct=0,
    )
    assert result["window_count"] == 3
    for window in result["windows"]:
        spec = window["selected_strategy_spec"]
        assert spec["schema_version"] == 1
        assert spec["strategy_type"] == "sma_cross"
        assert spec["params"] == window["selected_params"]
