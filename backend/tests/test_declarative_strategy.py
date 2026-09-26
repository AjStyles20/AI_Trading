import pandas as pd
import pytest

from core.declarative_strategy import StrategySpec, declarative_strategy_engine


def frame():
    return pd.DataFrame({
        "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "close": [100.0, 101.0, 103.0, 102.0, 105.0, 107.0],
    })


def test_sma_spec_produces_signal_and_execution_risk_columns():
    spec = StrategySpec("sma_cross", {
        "sma_fast": 2,
        "sma_slow": 3,
        "position_size_pct": 50,
        "stop_loss_pct": 2,
        "take_profit_pct": 4,
    })
    result = declarative_strategy_engine.execute(spec, frame())
    assert len(result) == 6
    assert set(result["signal"].dropna().unique()).issubset({-1, 0, 1})
    assert (result["position_size_pct"] == 50).all()
    assert (result["stop_loss_pct"] == 2).all()
    assert (result["take_profit_pct"] == 4).all()


def test_declarative_spec_rejects_unknown_strategy_type():
    with pytest.raises(ValueError, match="Unsupported declarative strategy"):
        StrategySpec("arbitrary_python", {})


def test_sma_spec_rejects_inverted_windows():
    spec = StrategySpec("sma_cross", {
        "sma_fast": 5,
        "sma_slow": 2,
        "position_size_pct": 50,
        "stop_loss_pct": 2,
        "take_profit_pct": 4,
    })
    with pytest.raises(ValueError, match="sma_fast"):
        declarative_strategy_engine.execute(spec, frame())


def test_declarative_risk_percentages_are_bounded():
    spec = StrategySpec("sma_cross", {
        "sma_fast": 2,
        "sma_slow": 3,
        "position_size_pct": 101,
        "stop_loss_pct": 2,
        "take_profit_pct": 4,
    })
    with pytest.raises(ValueError, match="position_size_pct"):
        declarative_strategy_engine.execute(spec, frame())



@pytest.mark.parametrize("cooldown", [-1, 1.5, True, "not-an-int"])
def test_declarative_cooldown_rejects_invalid_values(cooldown):
    spec = StrategySpec("sma_cross", {
        "sma_fast": 2,
        "sma_slow": 3,
        "position_size_pct": 50,
        "stop_loss_pct": 2,
        "take_profit_pct": 4,
        "cooldown_bars": cooldown,
    })
    with pytest.raises(ValueError, match="cooldown_bars must be a non-negative integer"):
        declarative_strategy_engine.execute(spec, frame())


@pytest.mark.parametrize("cooldown", [0, 2, "3"])
def test_declarative_cooldown_accepts_exact_nonnegative_integers(cooldown):
    spec = StrategySpec("sma_cross", {
        "sma_fast": 2,
        "sma_slow": 3,
        "position_size_pct": 50,
        "stop_loss_pct": 2,
        "take_profit_pct": 4,
        "cooldown_bars": cooldown,
    })
    result = declarative_strategy_engine.execute(spec, frame())
    assert (result["cooldown_bars"] == int(cooldown)).all()
