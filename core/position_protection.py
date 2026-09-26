from __future__ import annotations

from dataclasses import dataclass

from core.position_ledger import ConfirmedPosition


@dataclass(frozen=True)
class ProtectionDecision:
    should_exit: bool
    reason: str | None
    trigger_price: float | None
    market_price: float
    position_qty: float


def evaluate_position_protection(
    position: ConfirmedPosition,
    *,
    market_price: float,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
) -> ProtectionDecision:
    """Evaluate close-based long-position protection without submitting an order.

    Threshold semantics intentionally match the backtest engine:
    stop: close <= entry * (1 - stop_pct / 100)
    take: close >= entry * (1 + take_pct / 100)
    """
    market_price = float(market_price)
    stop_loss_pct = float(stop_loss_pct)
    take_profit_pct = float(take_profit_pct)

    if market_price <= 0:
        raise ValueError("market_price must be greater than zero.")
    for name, value in (("stop_loss_pct", stop_loss_pct), ("take_profit_pct", take_profit_pct)):
        if value < 0 or value > 100:
            raise ValueError(f"{name} must be between 0 and 100.")

    if position.qty <= 0:
        return ProtectionDecision(False, None, None, market_price, 0.0)
    if position.average_entry_price <= 0:
        raise ValueError("Open confirmed position requires a positive average_entry_price.")

    stop_price = (
        position.average_entry_price * (1 - stop_loss_pct / 100.0)
        if stop_loss_pct > 0 else None
    )
    take_price = (
        position.average_entry_price * (1 + take_profit_pct / 100.0)
        if take_profit_pct > 0 else None
    )

    # If both thresholds could mathematically trigger (for example a 100% stop
    # at zero combined with unusual inputs), protective loss containment takes
    # precedence.
    if stop_price is not None and market_price <= stop_price:
        return ProtectionDecision(True, "stop_loss", stop_price, market_price, position.qty)
    if take_price is not None and market_price >= take_price:
        return ProtectionDecision(True, "take_profit", take_price, market_price, position.qty)
    return ProtectionDecision(False, None, None, market_price, position.qty)
