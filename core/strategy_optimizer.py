import itertools
from typing import Any, Dict, List

import pandas as pd

from core.backtest_engine import backtest_engine


class StrategyOptimizer:
    def optimize(
        self,
        df: pd.DataFrame,
        strategy_type: str,
        custom_ranges: Dict[str, List[int]] | None = None,
        initial_balance: float = 10000.0,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.05,
    ) -> Dict[str, Any]:
        strategies = {
            "ema_rsi": self._ema_rsi_candidates,
            "sma_cross": self._sma_cross_candidates,
            "macd_rsi": self._macd_rsi_candidates,
        }

        candidate_builder = strategies.get(strategy_type, self._ema_rsi_candidates)
        candidates = candidate_builder(custom_ranges or {})
        results: List[Dict[str, Any]] = []

        for params in candidates:
            strategy_code = self._build_strategy_code(strategy_type, params)
            local_scope = {"pd": pd}
            exec(strategy_code, {}, local_scope)
            result_df = local_scope["strategy"](df.copy())
            metrics = backtest_engine.run_backtest(
                result_df,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            score = (
                metrics["total_return_pct"] * 0.55
                + metrics["win_rate_pct"] * 0.25
                + metrics["buy_hold_return_pct"] * 0.05
                - abs(metrics["max_drawdown_pct"]) * 0.35
            )
            results.append({
                "strategy_type": strategy_type,
                "params": params,
                "score": round(score, 3),
                "code": strategy_code,
                "metrics": {
                    "total_return_pct": round(metrics["total_return_pct"], 3),
                    "max_drawdown_pct": round(metrics["max_drawdown_pct"], 3),
                    "trade_count": metrics["trade_count"],
                    "final_equity": round(metrics["final_equity"], 2),
                    "buy_hold_return_pct": round(metrics["buy_hold_return_pct"], 3),
                    "win_rate_pct": round(metrics["win_rate_pct"], 3),
                },
            })

        ranked = sorted(results, key=lambda item: item["score"], reverse=True)
        return {
            "strategy_type": strategy_type,
            "best": ranked[0] if ranked else None,
            "results": ranked[:10],
        }

    def _sanitize_values(self, values: List[int] | None, defaults: List[int]) -> List[int]:
        if not values:
            return defaults
        cleaned = sorted({int(value) for value in values if int(value) > 0})
        return cleaned or defaults

    def _ema_rsi_candidates(self, custom_ranges: Dict[str, List[int]]) -> List[Dict[str, int]]:
        ema_fast = self._sanitize_values(custom_ranges.get("ema_fast"), [8, 12, 21])
        ema_slow = self._sanitize_values(custom_ranges.get("ema_slow"), [26, 34, 55])
        rsi_period = self._sanitize_values(custom_ranges.get("rsi_period"), [10, 14])
        rsi_buy = self._sanitize_values(custom_ranges.get("rsi_buy"), [25, 30, 35])
        rsi_sell = self._sanitize_values(custom_ranges.get("rsi_sell"), [65, 70, 75])
        stop_loss_pct = self._sanitize_values(custom_ranges.get("stop_loss_pct"), [2, 3, 5])
        take_profit_pct = self._sanitize_values(custom_ranges.get("take_profit_pct"), [4, 6, 8])
        cooldown_bars = self._sanitize_values(custom_ranges.get("cooldown_bars"), [0, 2, 4])
        position_size_pct = self._sanitize_values(custom_ranges.get("position_size_pct"), [25, 50, 100])
        return [
            {
                "ema_fast": fast,
                "ema_slow": slow,
                "rsi_period": rsi_period_value,
                "rsi_buy": buy,
                "rsi_sell": sell,
                "stop_loss_pct": stop_loss,
                "take_profit_pct": take_profit,
                "cooldown_bars": cooldown,
                "position_size_pct": size,
            }
            for fast, slow, rsi_period_value, buy, sell, stop_loss, take_profit, cooldown, size in itertools.product(
                ema_fast,
                ema_slow,
                rsi_period,
                rsi_buy,
                rsi_sell,
                stop_loss_pct,
                take_profit_pct,
                cooldown_bars,
                position_size_pct,
            )
            if fast < slow and buy < sell
        ]

    def _sma_cross_candidates(self, custom_ranges: Dict[str, List[int]]) -> List[Dict[str, int]]:
        sma_fast = self._sanitize_values(custom_ranges.get("sma_fast"), [5, 10, 20])
        sma_slow = self._sanitize_values(custom_ranges.get("sma_slow"), [30, 50, 100])
        stop_loss_pct = self._sanitize_values(custom_ranges.get("stop_loss_pct"), [2, 3, 5])
        take_profit_pct = self._sanitize_values(custom_ranges.get("take_profit_pct"), [4, 6, 8])
        cooldown_bars = self._sanitize_values(custom_ranges.get("cooldown_bars"), [0, 2, 4])
        position_size_pct = self._sanitize_values(custom_ranges.get("position_size_pct"), [25, 50, 100])
        return [
            {
                "sma_fast": fast,
                "sma_slow": slow,
                "stop_loss_pct": stop_loss,
                "take_profit_pct": take_profit,
                "cooldown_bars": cooldown,
                "position_size_pct": size,
            }
            for fast, slow, stop_loss, take_profit, cooldown, size in itertools.product(
                sma_fast,
                sma_slow,
                stop_loss_pct,
                take_profit_pct,
                cooldown_bars,
                position_size_pct,
            )
            if fast < slow
        ]

    def _macd_rsi_candidates(self, custom_ranges: Dict[str, List[int]]) -> List[Dict[str, int]]:
        rsi_period = self._sanitize_values(custom_ranges.get("rsi_period"), [10, 14])
        rsi_buy = self._sanitize_values(custom_ranges.get("rsi_buy"), [25, 30, 35])
        rsi_sell = self._sanitize_values(custom_ranges.get("rsi_sell"), [65, 70, 75])
        stop_loss_pct = self._sanitize_values(custom_ranges.get("stop_loss_pct"), [2, 3, 5])
        take_profit_pct = self._sanitize_values(custom_ranges.get("take_profit_pct"), [4, 6, 8])
        cooldown_bars = self._sanitize_values(custom_ranges.get("cooldown_bars"), [0, 2, 4])
        position_size_pct = self._sanitize_values(custom_ranges.get("position_size_pct"), [25, 50, 100])
        return [
            {
                "rsi_period": rsi_period_value,
                "rsi_buy": buy,
                "rsi_sell": sell,
                "stop_loss_pct": stop_loss,
                "take_profit_pct": take_profit,
                "cooldown_bars": cooldown,
                "position_size_pct": size,
            }
            for rsi_period_value, buy, sell, stop_loss, take_profit, cooldown, size in itertools.product(
                rsi_period,
                rsi_buy,
                rsi_sell,
                stop_loss_pct,
                take_profit_pct,
                cooldown_bars,
                position_size_pct,
            )
            if buy < sell
        ]

    def _build_strategy_code(self, strategy_type: str, params: Dict[str, int]) -> str:
        risk_block = f"""
    df['signal'] = df['signal'].fillna(0)
    df['position_size_pct'] = {params['position_size_pct']}
    in_position = False
    cooldown_remaining = 0
    entry_price = 0.0

    for idx in range(len(df)):
        current_price = float(df['close'].iloc[idx])
        raw_signal = int(df['signal'].iloc[idx])

        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            if not in_position:
                df.iloc[idx, df.columns.get_loc('signal')] = 0
                continue

        if in_position:
            stop_level = entry_price * (1 - {params['stop_loss_pct']} / 100)
            take_level = entry_price * (1 + {params['take_profit_pct']} / 100)
            if current_price <= stop_level or current_price >= take_level:
                df.iloc[idx, df.columns.get_loc('signal')] = -1
                in_position = False
                cooldown_remaining = {params['cooldown_bars']}
                continue

        if raw_signal == 1 and not in_position:
            entry_price = current_price
            in_position = True
        elif raw_signal == -1 and in_position:
            in_position = False
            cooldown_remaining = {params['cooldown_bars']}
"""
        if strategy_type == "sma_cross":
            return f"""import pandas as pd

def strategy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['sma_fast'] = df['close'].rolling({params['sma_fast']}).mean()
    df['sma_slow'] = df['close'].rolling({params['sma_slow']}).mean()
    df['signal'] = 0
    df.loc[df['sma_fast'] > df['sma_slow'], 'signal'] = 1
    df.loc[df['sma_fast'] < df['sma_slow'], 'signal'] = -1
{risk_block}
    return df
"""

        if strategy_type == "macd_rsi":
            return f"""import pandas as pd

def strategy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling({params['rsi_period']}).mean()
    loss = (-delta.clip(upper=0)).rolling({params['rsi_period']}).mean()
    rs = gain / loss.replace(0, pd.NA)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['signal'] = 0
    df.loc[(df['macd'] > df['macd_signal']) & (df['rsi'] < {params['rsi_buy']}), 'signal'] = 1
    df.loc[(df['macd'] < df['macd_signal']) & (df['rsi'] > {params['rsi_sell']}), 'signal'] = -1
{risk_block}
    return df
"""

        return f"""import pandas as pd

def strategy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span={params['ema_fast']}, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span={params['ema_slow']}, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling({params['rsi_period']}).mean()
    loss = (-delta.clip(upper=0)).rolling({params['rsi_period']}).mean()
    rs = gain / loss.replace(0, pd.NA)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['signal'] = 0
    df.loc[(df['ema_fast'] > df['ema_slow']) & (df['rsi'] < {params['rsi_buy']}), 'signal'] = 1
    df.loc[(df['ema_fast'] < df['ema_slow']) & (df['rsi'] > {params['rsi_sell']}), 'signal'] = -1
{risk_block}
    return df
"""


strategy_optimizer = StrategyOptimizer()
