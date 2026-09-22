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
    ) -> Dict[str, Any]:
        """
        Run a backtest on a DataFrame that must contain a 'signal' column.
        1: Buy, -1: Sell, 0: Hold
        """
        if 'signal' not in df.columns or 'close' not in df.columns:
            raise ValueError(f"DataFrame missing required columns. Found: {list(df.columns)}")

        balance = initial_balance
        position = 0.0
        trade_history = []
        equity_curve = [initial_balance]
        round_trip_pnls: List[float] = []
        fee_rate = max(fee_pct, 0) / 100
        slippage_rate = max(slippage_pct, 0) / 100
        last_buy_value = None

        for index in range(len(df)):
            price = float(df['close'].iloc[index])
            signal = df['signal'].iloc[index]
            position_size_pct = 100.0
            if 'position_size_pct' in df.columns:
                try:
                    position_size_pct = float(df['position_size_pct'].iloc[index])
                except Exception:
                    position_size_pct = 100.0
            allocation_rate = min(max(position_size_pct, 0.0), 100.0) / 100.0

            if signal == 1 and position == 0:
                executed_price = price * (1 + slippage_rate)
                capital_to_allocate = balance * allocation_rate
                entry_fee = capital_to_allocate * fee_rate
                position = max((capital_to_allocate - entry_fee) / executed_price, 0)
                balance = balance - capital_to_allocate
                last_buy_value = executed_price * position + entry_fee
                trade_history.append({
                    "type": "BUY",
                    "price": executed_price,
                    "timestamp": df.index[index],
                    "balance": balance,
                    "fee_paid": entry_fee,
                    "position_size_pct": position_size_pct,
                })
            elif signal == -1 and position > 0:
                executed_price = price * (1 - slippage_rate)
                gross_proceeds = position * executed_price
                exit_fee = gross_proceeds * fee_rate
                balance = gross_proceeds - exit_fee
                if last_buy_value is not None:
                    round_trip_pnls.append(balance - last_buy_value)
                position = 0
                trade_history.append({
                    "type": "SELL",
                    "price": executed_price,
                    "timestamp": df.index[index],
                    "balance": balance,
                    "fee_paid": exit_fee,
                })
                last_buy_value = None

            current_equity = balance + (position * price if position > 0 else 0)
            equity_curve.append(float(current_equity))

        final_equity = balance + (position * float(df['close'].iloc[-1]) if position > 0 else 0)
        total_return = ((final_equity - initial_balance) / initial_balance) * 100
        buy_hold_return = ((float(df['close'].iloc[-1]) - float(df['close'].iloc[0])) / float(df['close'].iloc[0])) * 100

        equity_series = pd.Series(equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100

        winners = len([pnl for pnl in round_trip_pnls if pnl > 0])
        win_rate = (winners / len(round_trip_pnls) * 100) if round_trip_pnls else 0.0

        return {
            "initial_balance": initial_balance,
            "final_equity": final_equity,
            "total_return_pct": total_return,
            "max_drawdown_pct": max_drawdown,
            "trade_count": len(trade_history),
            "trade_history": trade_history,
            "equity_curve": equity_curve,
            "buy_hold_return_pct": buy_hold_return,
            "win_rate_pct": win_rate,
            "fee_pct": fee_pct,
            "slippage_pct": slippage_pct,
        }


backtest_engine = BacktestEngine()
