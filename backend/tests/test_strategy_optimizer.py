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
