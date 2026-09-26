import itertools

import pandas as pd
from typing import Any, Dict, List

from core.backtest_engine import backtest_engine
from core.safe_strategy_runtime import safe_strategy_runtime


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
        if len(df) < 30:
            raise ValueError("At least 30 chronological rows are required for optimization.")
        split_at = int(len(df) * 0.8)
        development_df = df.iloc[:split_at].copy()
        holdout_df = df.iloc[split_at:].copy()
        results: List[Dict[str, Any]] = []

        for params in candidates:
            strategy_code = self._build_strategy_code(strategy_type, params)
            result_df = safe_strategy_runtime.execute(strategy_code, development_df)
            metrics = backtest_engine.run_backtest(
                result_df,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            closed_round_trips = int(metrics.get("closed_round_trips", 0))
            evidence_factor = min(closed_round_trips / 5.0, 1.0)
            raw_score = (
                metrics["total_return_pct"] * 0.60
                + metrics["win_rate_pct"] * 0.20
                - abs(metrics["max_drawdown_pct"]) * 0.40
            )
            score = raw_score * evidence_factor
            results.append({
                "strategy_type": strategy_type,
                "params": params,
                "score": round(score, 3),
                "raw_score": round(raw_score, 3),
                "evidence_factor": round(evidence_factor, 3),
                "closed_round_trips": closed_round_trips,
                "code": strategy_code,
                "metrics": {
                    "total_return_pct": round(metrics["total_return_pct"], 3),
                    "max_drawdown_pct": round(metrics["max_drawdown_pct"], 3),
                    "trade_count": metrics["trade_count"],
                    "final_equity": round(metrics["final_equity"], 2),
                    "buy_hold_return_pct": round(metrics["buy_hold_return_pct"], 3),
                    "win_rate_pct": round(metrics["win_rate_pct"], 3),
                    "closed_round_trips": closed_round_trips,
                    "profit_factor": metrics.get("profit_factor"),
                },
            })

        ranked = sorted(results, key=lambda item: item["score"], reverse=True)
        best = ranked[0] if ranked else None
        holdout = None
        if best is not None:
            holdout_df_with_signals = safe_strategy_runtime.execute(best["code"], holdout_df)
            holdout_metrics = backtest_engine.run_backtest(
                holdout_df_with_signals,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            holdout = {
                "params": best["params"],
                "metrics": {
                    "total_return_pct": round(holdout_metrics["total_return_pct"], 3),
                    "max_drawdown_pct": round(holdout_metrics["max_drawdown_pct"], 3),
                    "trade_count": holdout_metrics["trade_count"],
                    "final_equity": round(holdout_metrics["final_equity"], 2),
                    "buy_hold_return_pct": round(holdout_metrics["buy_hold_return_pct"], 3),
                    "win_rate_pct": round(holdout_metrics["win_rate_pct"], 3),
                },
            }
        return {
            "strategy_type": strategy_type,
            "method": "chronological_development_holdout",
            "selection_rows": len(development_df),
            "holdout_rows": len(holdout_df),
            "best": best,
            "holdout": holdout,
            "results": ranked[:10],
        }


    def walk_forward_optimize(
        self,
        df: pd.DataFrame,
        strategy_type: str,
        train_rows: int,
        test_rows: int,
        step_rows: int | None = None,
        custom_ranges: Dict[str, List[int]] | None = None,
        initial_balance: float = 10000.0,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.05,
        warmup_rows: int = 0,
    ) -> Dict[str, Any]:
        """Select parameters on each past training window, then evaluate once on unseen data."""
        if warmup_rows < 0:
            raise ValueError("warmup_rows must be non-negative.")
        if train_rows < 30 or test_rows < 5:
            raise ValueError("Walk-forward optimization requires train_rows >= 30 and test_rows >= 5.")
        step = step_rows or test_rows
        if step < test_rows:
            raise ValueError("step_rows must be >= test_rows to prevent overlapping OOS test windows.")
        if len(df) < train_rows + test_rows:
            raise ValueError("Dataset is too short for one complete walk-forward optimization window.")

        windows: List[Dict[str, Any]] = []
        start = 0
        window_id = 1
        while start + train_rows + test_rows <= len(df):
            train_df = df.iloc[start:start + train_rows].copy()
            test_df = df.iloc[start + train_rows:start + train_rows + test_rows].copy()

            selection = self.optimize(
                train_df,
                strategy_type=strategy_type,
                custom_ranges=custom_ranges,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            best = selection.get("best")
            if best is None:
                raise ValueError(f"No candidate strategy was selected in walk-forward window {window_id}.")

            test_start_position = start + train_rows
            if warmup_rows:
                context_start = max(0, test_start_position - warmup_rows)
                context = df.iloc[context_start:test_start_position + test_rows].copy()
                test_with_context = safe_strategy_runtime.execute(best["code"], context)
                test_signals = test_with_context.iloc[-test_rows:].copy()
            else:
                test_signals = safe_strategy_runtime.execute(best["code"], test_df)
            test_metrics = backtest_engine.run_backtest(
                test_signals,
                initial_balance=initial_balance,
                fee_pct=fee_pct,
                slippage_pct=slippage_pct,
            )
            windows.append({
                "window": window_id,
                "train_start": str(train_df.index[0]),
                "train_end": str(train_df.index[-1]),
                "test_start": str(test_df.index[0]),
                "test_end": str(test_df.index[-1]),
                "selected_params": best["params"],
                "selection_score": best["score"],
                "test_metrics": test_metrics,
            })
            start += step
            window_id += 1

        returns = [window["test_metrics"]["total_return_pct"] for window in windows]
        drawdowns = [window["test_metrics"]["max_drawdown_pct"] for window in windows]
        return {
            "method": "rolling_walk_forward_parameter_selection",
            "selection_policy": "parameters are selected using each past training window only, frozen, then evaluated once on the following unseen test window",
            "strategy_type": strategy_type,
            "train_rows": train_rows,
            "test_rows": test_rows,
            "step_rows": step,
            "warmup_rows": warmup_rows,
            "warmup_policy": "past-only context initializes the selected strategy for OOS execution; OOS rows never participate in parameter selection",
            "window_count": len(windows),
            "summary": {
                "mean_test_return_pct": round(sum(returns) / len(returns), 4),
                "positive_test_windows": sum(value > 0 for value in returns),
                "worst_test_drawdown_pct": round(min(drawdowns), 4),
            },
            "windows": windows,
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
            return f"""def strategy(df: pd.DataFrame) -> pd.DataFrame:
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
            return f"""def strategy(df: pd.DataFrame) -> pd.DataFrame:
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

        return f"""def strategy(df: pd.DataFrame) -> pd.DataFrame:
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
