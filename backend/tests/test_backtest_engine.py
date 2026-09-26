import pytest
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


@pytest.mark.parametrize(
    "column,values,error_fragment",
    [
        ("close", [100.0, float("nan")], "missing or non-numeric"),
        ("close", [100.0, 0.0], "positive values"),
        ("signal", [1, 2], "unsupported values"),
    ],
)
def test_backtest_rejects_invalid_market_inputs(column, values, error_fragment):
    data = {
        "open": [100.0, 100.0],
        "close": [100.0, 100.0],
        "signal": [1, 0],
    }
    data[column] = values
    df = pd.DataFrame(data)
    with pytest.raises(ValueError, match=error_fragment):
        BacktestEngine().run_backtest(df, execution_delay_bars=0)


def test_backtest_rejects_reverse_chronological_data():
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "close": [100.0, 101.0],
            "signal": [1, 0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-01"]),
    )
    with pytest.raises(ValueError, match="oldest to newest"):
        BacktestEngine().run_backtest(df)


def test_backtest_rejects_duplicate_timestamps():
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "close": [100.0, 101.0],
            "signal": [1, 0],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-01"]),
    )
    with pytest.raises(ValueError, match="duplicate timestamps"):
        BacktestEngine().run_backtest(df)


def test_execution_delay_prevents_same_bar_signal_fill():
    df = pd.DataFrame({
        "open": [100.0, 200.0],
        "close": [100.0, 200.0],
        "signal": [1, 0],
    })
    delayed = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=1
    )
    immediate = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=0
    )
    assert delayed["trade_history"][0]["price"] == 200.0
    assert immediate["trade_history"][0]["price"] == 100.0
    assert delayed["final_equity"] < immediate["final_equity"]


def test_stop_loss_is_anchored_to_actual_fill_and_exits_next_bar():
    df = pd.DataFrame({
        "open": [100.0, 110.0, 108.0, 100.0],
        "close": [100.0, 110.0, 104.0, 100.0],
        "signal": [1, 0, 0, 0],
        "stop_loss_pct": [5.0] * 4,
        "take_profit_pct": [0.0] * 4,
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=1
    )
    assert result["trade_history"][0]["price"] == 110.0
    # 5% below the real 110 fill is 104.5; bar 2 closes at 104 and triggers.
    # Because that close is only known after bar 2, execution occurs at bar 3 open.
    assert result["trade_history"][1]["price"] == 100.0
    assert result["trade_history"][1]["exit_reason"] == "risk"


def test_stop_loss_does_not_use_signal_bar_close_as_entry_anchor():
    df = pd.DataFrame({
        "open": [100.0, 110.0, 108.0, 108.0],
        "close": [100.0, 110.0, 106.0, 108.0],
        "signal": [1, 0, 0, 0],
        "stop_loss_pct": [5.0] * 4,
        "take_profit_pct": [0.0] * 4,
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=1
    )
    # A fictional 100 entry would not stop at 106; the real 110 fill does (threshold 104.5 is not hit).
    # Therefore this path remains open and proves the engine is not using the signal close.
    assert result["trade_history"][0]["price"] == 110.0
    assert len(result["trade_history"]) == 1


def test_take_profit_uses_fill_price_and_next_bar_execution():
    df = pd.DataFrame({
        "open": [100.0, 100.0, 104.0, 107.0],
        "close": [100.0, 100.0, 106.0, 107.0],
        "signal": [1, 0, 0, 0],
        "stop_loss_pct": [0.0] * 4,
        "take_profit_pct": [5.0] * 4,
    })
    result = BacktestEngine().run_backtest(
        df, initial_balance=10000, fee_pct=0, slippage_pct=0, execution_delay_bars=1
    )
    assert result["trade_history"][0]["price"] == 100.0
    assert result["trade_history"][1]["price"] == 107.0
    assert result["trade_history"][1]["exit_reason"] == "risk"



def test_cooldown_blocks_exact_number_of_full_bars_after_exit_fill():
    import pandas as pd
    from core.backtest_engine import backtest_engine

    idx = pd.date_range("2026-01-01", periods=7, freq="h")
    df = pd.DataFrame({
        "open": [100.0] * 7,
        "close": [100.0] * 7,
        "signal": [1, -1, 1, 1, 1, 0, 0],
        "cooldown_bars": [2] * 7,
    }, index=idx)

    result = backtest_engine.run_backtest(
        df, fee_pct=0, slippage_pct=0, execution_delay_bars=1
    )
    buys = [trade for trade in result["trade_history"] if trade["type"] == "BUY"]
    sells = [trade for trade in result["trade_history"] if trade["type"] == "SELL"]

    assert sells[0]["timestamp"] == idx[2]
    assert [trade["timestamp"] for trade in buys] == [idx[1], idx[5]]


def test_zero_cooldown_allows_next_eligible_buy_fill():
    import pandas as pd
    from core.backtest_engine import backtest_engine

    idx = pd.date_range("2026-01-01", periods=5, freq="h")
    df = pd.DataFrame({
        "open": [100.0] * 5,
        "close": [100.0] * 5,
        "signal": [1, -1, 1, 0, 0],
        "cooldown_bars": [0] * 5,
    }, index=idx)

    result = backtest_engine.run_backtest(
        df, fee_pct=0, slippage_pct=0, execution_delay_bars=1
    )
    buys = [trade for trade in result["trade_history"] if trade["type"] == "BUY"]
    assert [trade["timestamp"] for trade in buys] == [idx[1], idx[3]]


@pytest.mark.parametrize("bad_value", [-1, 1.5])
def test_backtest_rejects_invalid_cooldown_values_after_exit(bad_value):
    import pandas as pd
    from core.backtest_engine import backtest_engine

    idx = pd.date_range("2026-01-01", periods=4, freq="h")
    df = pd.DataFrame({
        "open": [100.0] * 4,
        "close": [100.0] * 4,
        "signal": [1, -1, 0, 0],
        "cooldown_bars": [bad_value] * 4,
    }, index=idx)

    with pytest.raises(ValueError, match="cooldown_bars"):
        backtest_engine.run_backtest(
            df, fee_pct=0, slippage_pct=0, execution_delay_bars=1
        )



def test_risk_exit_starts_same_fill_based_cooldown():
    import pandas as pd
    from core.backtest_engine import backtest_engine

    idx = pd.date_range("2026-01-01", periods=7, freq="h")
    df = pd.DataFrame({
        "open": [100.0, 100.0, 100.0, 94.0, 100.0, 100.0, 100.0],
        "close": [100.0, 100.0, 94.0, 94.0, 100.0, 100.0, 100.0],
        "signal": [1, 0, 1, 1, 1, 1, 0],
        "stop_loss_pct": [5.0] * 7,
        "take_profit_pct": [0.0] * 7,
        "cooldown_bars": [2] * 7,
    }, index=idx)

    result = backtest_engine.run_backtest(
        df, fee_pct=0, slippage_pct=0, execution_delay_bars=1
    )
    buys = [trade for trade in result["trade_history"] if trade["type"] == "BUY"]
    sells = [trade for trade in result["trade_history"] if trade["type"] == "SELL"]

    assert sells[0]["timestamp"] == idx[3]
    assert sells[0]["exit_reason"] == "risk"
    assert [trade["timestamp"] for trade in buys] == [idx[1], idx[6]]
