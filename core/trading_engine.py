import pandas as pd
import numpy as np
from core.strategy_execution import execute_strategy_record
from typing import Dict, Any, Optional

class TradingEngine:
    def __init__(self):
        self.active_positions = {} # symbol -> position_data

    def evaluate_strategy(self, strategy, df: pd.DataFrame) -> pd.DataFrame:
        """Execute an explicit strategy record, retaining raw-code compatibility."""
        if isinstance(strategy, str):
            strategy = {
                "strategy_format": "legacy_python",
                "strategy_spec": {},
                "code": strategy,
            }
        if not isinstance(strategy, dict):
            raise TypeError("strategy must be a persisted strategy record or legacy Python code")
        result = execute_strategy_record(strategy, df)
        if not isinstance(result, pd.DataFrame):
            raise TypeError("strategy(df) must return a pandas DataFrame")
        if result.empty:
            raise ValueError("strategy(df) returned an empty DataFrame")
        return result

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
