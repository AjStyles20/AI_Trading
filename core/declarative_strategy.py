from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

import pandas as pd


SUPPORTED_TYPES = {"sma_cross", "macd_rsi", "ema_rsi"}


@dataclass(frozen=True)
class StrategySpec:
    """Declarative strategy definition with no executable user code."""

    strategy_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported strategy schema_version.")
        if self.strategy_type not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported declarative strategy type: {self.strategy_type}")


class DeclarativeStrategyEngine:
    def execute(self, spec: StrategySpec, df: pd.DataFrame) -> pd.DataFrame:
        if "close" not in df.columns:
            raise ValueError("Declarative strategy requires a 'close' column.")
        out = df.copy()
        p = spec.params
        out["signal"] = 0

        if spec.strategy_type == "sma_cross":
            fast = self._positive_int(p, "sma_fast")
            slow = self._positive_int(p, "sma_slow")
            if fast >= slow:
                raise ValueError("sma_fast must be less than sma_slow.")
            out["sma_fast"] = out["close"].rolling(fast).mean()
            out["sma_slow"] = out["close"].rolling(slow).mean()
            out.loc[out["sma_fast"] > out["sma_slow"], "signal"] = 1
            out.loc[out["sma_fast"] < out["sma_slow"], "signal"] = -1
        elif spec.strategy_type == "macd_rsi":
            rsi_period = self._positive_int(p, "rsi_period")
            out["ema_fast"] = out["close"].ewm(span=12, adjust=False).mean()
            out["ema_slow"] = out["close"].ewm(span=26, adjust=False).mean()
            out["macd"] = out["ema_fast"] - out["ema_slow"]
            out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
            out["rsi"] = self._rsi(out["close"], rsi_period)
            buy = float(p["rsi_buy"])
            sell = float(p["rsi_sell"])
            out.loc[(out["macd"] > out["macd_signal"]) & (out["rsi"] < buy), "signal"] = 1
            out.loc[(out["macd"] < out["macd_signal"]) & (out["rsi"] > sell), "signal"] = -1
        else:
            fast = self._positive_int(p, "ema_fast")
            slow = self._positive_int(p, "ema_slow")
            if fast >= slow:
                raise ValueError("ema_fast must be less than ema_slow.")
            rsi_period = self._positive_int(p, "rsi_period")
            out["ema_fast"] = out["close"].ewm(span=fast, adjust=False).mean()
            out["ema_slow"] = out["close"].ewm(span=slow, adjust=False).mean()
            out["rsi"] = self._rsi(out["close"], rsi_period)
            buy = float(p["rsi_buy"])
            sell = float(p["rsi_sell"])
            out.loc[(out["ema_fast"] > out["ema_slow"]) & (out["rsi"] < buy), "signal"] = 1
            out.loc[(out["ema_fast"] < out["ema_slow"]) & (out["rsi"] > sell), "signal"] = -1

        out["position_size_pct"] = self._bounded_pct(p, "position_size_pct", allow_zero=False)
        out["stop_loss_pct"] = self._bounded_pct(p, "stop_loss_pct")
        out["take_profit_pct"] = self._bounded_pct(p, "take_profit_pct")
        out["cooldown_bars"] = self._nonnegative_int(p, "cooldown_bars")
        return out

    @staticmethod
    def _positive_int(params: Dict[str, Any], key: str) -> int:
        value = int(params[key])
        if value <= 0:
            raise ValueError(f"{key} must be positive.")
        return value

    @staticmethod
    def _nonnegative_int(params: Dict[str, Any], key: str) -> int:
        raw = params.get(key, 0)
        if isinstance(raw, bool):
            raise ValueError(f"{key} must be a non-negative integer.")
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a non-negative integer.") from None
        if not numeric.is_integer() or numeric < 0:
            raise ValueError(f"{key} must be a non-negative integer.")
        return int(numeric)

    @staticmethod
    def _bounded_pct(params: Dict[str, Any], key: str, allow_zero: bool = True) -> float:
        value = float(params[key])
        lower = 0.0 if allow_zero else 0.000001
        if value < lower or value > 100:
            raise ValueError(f"{key} must be between {lower} and 100.")
        return value

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, pd.NA)
        return 100 - (100 / (1 + rs))


declarative_strategy_engine = DeclarativeStrategyEngine()
