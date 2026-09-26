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


def test_open_position_final_equity_uses_liquidation_costs():
    df = pd.DataFrame({
        "open": [100.0, 100.0],
        "close": [100.0, 100.0],
        "signal": [1, 0],
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=1.0, slippage_pct=1.0, execution_delay_bars=0
    )
    assert result["open_position_at_end"] is True
    assert result["final_liquidation_fee"] > 0
    assert result["total_fees_paid"] > result["final_liquidation_fee"]
    assert result["final_equity"] < 10000.0


def test_closed_trade_reports_realized_pnl_and_round_trip_count():
    df = pd.DataFrame({
        "open": [100.0, 110.0],
        "close": [100.0, 110.0],
        "signal": [1, -1],
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=0
    )
    assert result["closed_round_trips"] == 1
    assert result["realized_pnl"] == 1000.0
    assert result["open_position_at_end"] is False
    assert result["final_liquidation_value"] == 0.0


def test_terminal_liquidation_cost_is_not_added_to_trade_count():
    df = pd.DataFrame({
        "open": [100.0, 100.0],
        "close": [100.0, 110.0],
        "signal": [1, 0],
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0.1, slippage_pct=0.1, execution_delay_bars=0
    )
    assert result["trade_count"] == 1
    assert result["closed_round_trips"] == 0
    assert result["final_liquidation_value"] > 0


def test_equity_curve_ends_at_final_liquidation_equity():
    df = pd.DataFrame({
        "open": [100.0, 100.0, 110.0],
        "close": [100.0, 105.0, 110.0],
        "signal": [1, 0, 0],
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0.5, slippage_pct=0.5, execution_delay_bars=0
    )
    assert result["equity_curve"][-1] == result["final_equity"]
    assert result["max_drawdown_pct"] <= 0


def test_profit_factor_uses_closed_round_trip_pnl():
    df = pd.DataFrame({
        "open": [100.0, 110.0, 100.0, 95.0],
        "close": [100.0, 110.0, 100.0, 95.0],
        "signal": [1, -1, 1, -1],
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=0
    )
    assert result["closed_round_trips"] == 2
    assert result["profit_factor"] is not None
    assert result["profit_factor"] > 0
    assert result["return_volatility_pct_per_bar"] >= 0
