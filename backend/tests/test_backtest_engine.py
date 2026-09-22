import pandas as pd

from core.backtest_engine import BacktestEngine


def test_partial_allocation_preserves_uninvested_cash():
    df = pd.DataFrame({
        "open": [100.0, 100.0, 110.0, 110.0],
        "close": [100.0, 100.0, 110.0, 110.0],
        "signal": [1, 0, -1, 0],
        "position_size_pct": [50.0, 50.0, 50.0, 50.0],
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=0
    )
    assert result["final_equity"] == 10500.0


def test_default_executes_signal_on_next_bar_open():
    df = pd.DataFrame({
        "open": [100.0, 105.0, 120.0],
        "close": [100.0, 110.0, 120.0],
        "signal": [1, -1, 0],
        "position_size_pct": [100.0, 100.0, 100.0],
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0
    )
    assert result["trade_history"][0]["price"] == 105.0
    assert result["trade_history"][1]["price"] == 120.0
    assert result["final_equity"] > 10000


def test_fees_and_slippage_reduce_equity():
    df = pd.DataFrame({
        "open": [100.0, 100.0, 100.0],
        "close": [100.0, 100.0, 100.0],
        "signal": [1, -1, 0],
    })
    clean = BacktestEngine().run_backtest(df, fee_pct=0, slippage_pct=0)
    costly = BacktestEngine().run_backtest(df, fee_pct=0.1, slippage_pct=0.1)
    assert costly["final_equity"] < clean["final_equity"]
