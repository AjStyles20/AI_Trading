"""What the user is looking at, sent with each chat message so the AI can see it.

The desktop app sends this snapshot; it is untrusted input. Every field is
bounded and every number must be finite, so the prompt never carries NaN,
infinity or arbitrary text from the request beyond a validated symbol.
"""
from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

INDICATOR_LABELS = {
    "sma20": "SMA 20",
    "ema21": "EMA 21",
    "rsi14": "RSI 14",
    "macd": "MACD",
    "macd_signal": "MACD signal",
    "bb_upper": "Bollinger upper",
    "bb_lower": "Bollinger lower",
    "atr14": "ATR 14",
}

class BacktestSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    interval: Optional[Literal["1m", "5m", "15m", "1h", "4h", "1d"]] = None
    period: Optional[Literal["1mo", "3mo", "6mo", "1y", "2y"]] = None
    total_return_pct: float = Field(allow_inf_nan=False)
    max_drawdown_pct: float = Field(allow_inf_nan=False)
    buy_hold_return_pct: Optional[float] = Field(default=None, allow_inf_nan=False)
    win_rate_pct: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    trade_count: int = Field(ge=0, le=1_000_000)


class WorkspaceContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(pattern=r"^[A-Za-z0-9^][A-Za-z0-9.=^/-]{0,19}$")
    asset_type: Literal["crypto", "stock"]
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1D"]
    last_price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    change_24h_pct: Optional[float] = Field(default=None, allow_inf_nan=False)
    price_source: Optional[Literal["binance", "backend"]] = None
    indicators: dict[str, float] = Field(default_factory=dict)
    backtest: Optional[BacktestSnapshot] = None

    @field_validator("indicators")
    @classmethod
    def _known_finite_indicators(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = sorted(set(value) - set(INDICATOR_LABELS))
        if unknown:
            raise ValueError(f"Unknown indicators: {unknown}")
        if not all(math.isfinite(number) for number in value.values()):
            raise ValueError("Indicator values must be finite numbers.")
        return value


def _number(value: float) -> str:
    return f"{value:,.6g}" if abs(value) < 1 else f"{value:,.2f}"


def format_workspace_context(context: Optional[WorkspaceContext]) -> str:
    """A short, plainly labelled block for the system prompt, or '' when absent."""
    if context is None:
        return ""
    source = {"binance": "Binance live stream", "backend": "Yahoo Finance, may lag"}.get(context.price_source or "", "app")
    lines = [
        "Current workspace (a snapshot from the user's screen when they sent this message; use only these figures, do not extrapolate):",
        f"- Symbol: {context.symbol.upper()} ({context.asset_type}), timeframe {context.timeframe}",
    ]
    if context.last_price is not None:
        change = f", {context.change_24h_pct:+.2f}% over 24h" if context.change_24h_pct is not None else ""
        lines.append(f"- Last price: {_number(context.last_price)}{change} (source: {source})")
    if context.indicators:
        values = ", ".join(
            f"{INDICATOR_LABELS[key]} {_number(value)}" for key, value in context.indicators.items()
        )
        lines.append(f"- Indicators on completed and current candles: {values}")
    if context.backtest is not None:
        bt = context.backtest
        scenario = " ".join(part for part in (bt.period, bt.interval) if part)
        details = [
            f"return {bt.total_return_pct:+.2f}%",
            f"max drawdown {bt.max_drawdown_pct:.2f}%",
            f"{bt.trade_count} trades",
        ]
        if bt.win_rate_pct is not None:
            details.append(f"win rate {bt.win_rate_pct:.1f}%")
        if bt.buy_hold_return_pct is not None:
            details.append(f"buy & hold {bt.buy_hold_return_pct:+.2f}%")
        lines.append(f"- Latest backtest{f' ({scenario})' if scenario else ''}: {', '.join(details)}")
    return "\n".join(lines)
