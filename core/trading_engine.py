import pandas as pd
import numpy as np
from core.safe_strategy_runtime import safe_strategy_runtime
from typing import Dict, Any, Optional

class TradingEngine:
    def __init__(self):
        self.active_positions = {} # symbol -> position_data

    def evaluate_strategy(self, strategy_code: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        Executes the provided strategy code on the given DataFrame.
        Expects a function named 'strategy(df)' that returns the modified DataFrame.
        """
        try:
            return safe_strategy_runtime.execute(strategy_code, df)
        except Exception as e:
            print(f"ERROR in strategy evaluation: {e}")
            return df

    def get_signal(self, df: pd.DataFrame) -> Optional[str]:
        """
        Interprets the last row of the result DataFrame to determine a signal.
        Expects a 'signal' or 'target' column.
        1 = BUY, -1 = SELL, 0 = HOLD
        """
        if df.empty:
            return None
            
        last_row = df.iloc[-1]
        
        # Check common signal column names
        signal_col = None
        for col in ['signal', 'trade', 'action', 'position']:
            if col in df.columns:
                signal_col = col
                break
        
        if signal_col is None:
            return None
            
        val = last_row[signal_col]
        
        if val == 1 or val == 'BUY':
            return 'BUY'
        elif val == -1 or val == 'SELL':
            return 'SELL'
        
        return None

trading_engine = TradingEngine()
