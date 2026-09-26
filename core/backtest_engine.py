import pandas as pd
from typing import Dict, Any, List


class BacktestEngine:
    def __init__(self):
        self.initial_capital = 10000.0

    def run_backtest(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.05,
        execution_delay_bars: int = 1,
    ) -> Dict[str, Any]:
        """
        Run a backtest on a DataFrame that must contain a 'signal' column.
        1: Buy, -1: Sell, 0: Hold
        """
        if 'signal' not in df.columns or 'close' not in df.columns:
            raise ValueError(f"DataFrame missing required columns. Found: {list(df.columns)}")
        if df.empty:
            raise ValueError("Backtest requires at least one market-data row.")
        if initial_balance <= 0:
            raise ValueError("initial_balance must be greater than zero.")
        if fee_pct < 0 or slippage_pct < 0:
            raise ValueError("fee_pct and slippage_pct must be non-negative.")
        if execution_delay_bars < 0:
            raise ValueError("execution_delay_bars must be non-negative.")

        price_columns = ["close"]
        if execution_delay_bars > 0 and "open" in df.columns:
            price_columns.append("open")
        for column in price_columns:
            numeric = pd.to_numeric(df[column], errors="coerce")
            if numeric.isna().any():
                raise ValueError(f"Price column '{column}' contains missing or non-numeric values.")
            if (numeric <= 0).any():
                raise ValueError(f"Price column '{column}' must contain only positive values.")

        signals = pd.to_numeric(df["signal"], errors="coerce")
        if signals.isna().any():
            raise ValueError("Signal column contains missing or non-numeric values.")
        invalid_signals = sorted(set(signals[~signals.isin([-1, 0, 1])].tolist()))
        if invalid_signals:
            raise ValueError(f"Signal column contains unsupported values: {invalid_signals}. Expected -1, 0, or 1.")

        if not df.index.is_monotonic_increasing:
            raise ValueError("Market data index must be ordered from oldest to newest.")
        if df.index.has_duplicates:
            raise ValueError("Market data index must not contain duplicate timestamps.")

        balance = initial_balance
        position = 0.0
        trade_history = []
        equity_curve = [initial_balance]
        round_trip_pnls: List[float] = []
        fee_rate = max(fee_pct, 0) / 100
        slippage_rate = max(slippage_pct, 0) / 100
        last_buy_value = None
        entry_fill_price = None
        pending_risk_exit = False

        execution_delay_bars = int(execution_delay_bars)

        for index in range(len(df)):
            signal_index = index - execution_delay_bars
            signal = df['signal'].iloc[signal_index] if signal_index >= 0 else 0
            price_column = 'open' if execution_delay_bars > 0 and 'open' in df.columns else 'close'
            price = float(df[price_column].iloc[index])
            position_size_pct = 100.0
            if 'position_size_pct' in df.columns:
                try:
                    position_size_pct = float(df['position_size_pct'].iloc[index])
                except Exception:
                    position_size_pct = 100.0
            allocation_rate = min(max(position_size_pct, 0.0), 100.0) / 100.0

            risk_exit = pending_risk_exit
            pending_risk_exit = False

            if signal == 1 and position == 0:
                executed_price = price * (1 + slippage_rate)
                capital_to_allocate = balance * allocation_rate
                entry_fee = capital_to_allocate * fee_rate
                position = max((capital_to_allocate - entry_fee) / executed_price, 0)
                balance = balance - capital_to_allocate
                last_buy_value = executed_price * position + entry_fee
                entry_fill_price = executed_price
                trade_history.append({
                    "type": "BUY",
                    "price": executed_price,
                    "timestamp": df.index[index],
                    "balance": balance,
                    "fee_paid": entry_fee,
                    "position_size_pct": position_size_pct,
                })
            elif (signal == -1 or risk_exit) and position > 0:
                executed_price = price * (1 - slippage_rate)
                gross_proceeds = position * executed_price
                exit_fee = gross_proceeds * fee_rate
                net_proceeds = gross_proceeds - exit_fee
                balance += net_proceeds
                if last_buy_value is not None:
                    round_trip_pnls.append(net_proceeds - last_buy_value)
                position = 0
                trade_history.append({
                    "type": "SELL",
                    "price": executed_price,
                    "timestamp": df.index[index],
                    "balance": balance,
                    "fee_paid": exit_fee,
                    "exit_reason": "risk" if risk_exit and signal != -1 else "signal",
                })
                last_buy_value = None
                entry_fill_price = None

            if position > 0 and entry_fill_price is not None:
                stop_pct = float(df['stop_loss_pct'].iloc[index]) if 'stop_loss_pct' in df.columns else 0.0
                take_pct = float(df['take_profit_pct'].iloc[index]) if 'take_profit_pct' in df.columns else 0.0
                current_close = float(df['close'].iloc[index])
                stop_hit = stop_pct > 0 and current_close <= entry_fill_price * (1 - stop_pct / 100)
                take_hit = take_pct > 0 and current_close >= entry_fill_price * (1 + take_pct / 100)
                pending_risk_exit = stop_hit or take_hit

            if position > 0:
                mark_price = float(df['close'].iloc[index])
                liquidation_price = mark_price * (1 - slippage_rate)
                liquidation_gross = position * liquidation_price
                liquidation_fee_mark = liquidation_gross * fee_rate
                current_equity = balance + liquidation_gross - liquidation_fee_mark
            else:
                current_equity = balance
            equity_curve.append(float(current_equity))

        open_position = position > 0
        unrealized_position_qty = float(position)
        final_mark_price = float(df['close'].iloc[-1])
        liquidation_value = 0.0
        liquidation_fee = 0.0
        if open_position:
            liquidation_price = final_mark_price * (1 - slippage_rate)
            liquidation_gross = position * liquidation_price
            liquidation_fee = liquidation_gross * fee_rate
            liquidation_value = liquidation_gross - liquidation_fee

        final_equity = balance + liquidation_value if open_position else balance
        total_return = ((final_equity - initial_balance) / initial_balance) * 100
        buy_hold_return = ((float(df['close'].iloc[-1]) - float(df['close'].iloc[0])) / float(df['close'].iloc[0])) * 100

        equity_curve[-1] = float(final_equity)
        equity_series = pd.Series(equity_curve, dtype="float64")
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min() * 100)

        period_returns = equity_series.pct_change().replace([float("inf"), float("-inf")], pd.NA).dropna()
        return_volatility_pct = float(period_returns.std(ddof=0) * 100) if len(period_returns) else 0.0
        downside = period_returns[period_returns < 0]
        downside_volatility_pct = float(downside.std(ddof=0) * 100) if len(downside) else 0.0
        profit_factor = None
        gross_profit = float(sum(pnl for pnl in round_trip_pnls if pnl > 0))
        gross_loss = float(abs(sum(pnl for pnl in round_trip_pnls if pnl < 0)))
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = None

        winners = len([pnl for pnl in round_trip_pnls if pnl > 0])
        win_rate = (winners / len(round_trip_pnls) * 100) if round_trip_pnls else 0.0
        realized_pnl = float(sum(round_trip_pnls))
        total_fees_paid = float(sum(float(trade.get("fee_paid", 0.0)) for trade in trade_history) + liquidation_fee)
        closed_round_trips = len(round_trip_pnls)

        return {
            "initial_balance": initial_balance,
            "final_equity": final_equity,
            "total_return_pct": total_return,
            "max_drawdown_pct": max_drawdown,
            "return_volatility_pct_per_bar": return_volatility_pct,
            "downside_volatility_pct_per_bar": downside_volatility_pct,
            "profit_factor": profit_factor,
            "trade_count": len(trade_history),
            "trade_history": trade_history,
            "equity_curve": equity_curve,
            "buy_hold_return_pct": buy_hold_return,
            "win_rate_pct": win_rate,
            "realized_pnl": realized_pnl,
            "closed_round_trips": closed_round_trips,
            "total_fees_paid": total_fees_paid,
            "open_position_at_end": open_position,
            "open_position_qty": unrealized_position_qty if open_position else 0.0,
            "final_mark_price": final_mark_price,
            "final_liquidation_value": liquidation_value,
            "final_liquidation_fee": liquidation_fee,
            "fee_pct": fee_pct,
            "slippage_pct": slippage_pct,
            "execution_delay_bars": execution_delay_bars,
        }


backtest_engine = BacktestEngine()
