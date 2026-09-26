from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ConfirmedPosition:
    symbol: str
    broker_id: str
    execution_mode: str
    qty: float
    average_entry_price: float
    cost_basis: float


def reconstruct_confirmed_position(
    trades: Iterable[dict[str, Any]],
    *,
    symbol: str,
    broker_id: str,
    execution_mode: str,
) -> ConfirmedPosition:
    """Reconstruct the remaining long position from Astral's confirmed cumulative fills.

    Each persisted trade row represents one broker order and stores cumulative
    filled_qty/filled_price. Rows are consumed oldest-first. SELL fills reduce
    existing BUY lots FIFO. Test orders and other broker/mode/symbol scopes are
    ignored. This ledger is long-only; an oversell is rejected as inconsistent
    execution history rather than silently creating a short position.
    """
    scoped = [
        trade for trade in trades
        if not trade.get("is_test")
        and trade.get("symbol") == symbol
        and trade.get("broker_id", "paper") == broker_id
        and trade.get("execution_mode", "paper") == execution_mode
        and float(trade.get("filled_qty") or 0) > 0
    ]
    scoped.sort(key=lambda trade: (str(trade.get("timestamp") or ""), int(trade.get("id") or 0)))

    lots: list[list[float]] = []
    epsilon = 1e-12

    for trade in scoped:
        side = str(trade.get("side", "")).upper()
        qty = float(trade.get("filled_qty") or 0)
        price = float(trade.get("filled_price") or 0)
        if qty <= 0:
            continue
        if price <= 0:
            raise ValueError("Confirmed fills require a positive filled_price.")

        if side == "BUY":
            lots.append([qty, price])
            continue
        if side != "SELL":
            raise ValueError(f"Unsupported confirmed trade side: {side or '<empty>'}.")

        remaining = qty
        while remaining > epsilon and lots:
            lot_qty, lot_price = lots[0]
            consumed = min(lot_qty, remaining)
            lot_qty -= consumed
            remaining -= consumed
            if lot_qty <= epsilon:
                lots.pop(0)
            else:
                lots[0] = [lot_qty, lot_price]
        if remaining > epsilon:
            raise ValueError("Confirmed SELL fills exceed reconstructed long position.")

    position_qty = sum(qty for qty, _ in lots)
    cost_basis = sum(qty * price for qty, price in lots)
    average_entry_price = cost_basis / position_qty if position_qty > epsilon else 0.0
    return ConfirmedPosition(
        symbol=symbol,
        broker_id=broker_id,
        execution_mode=execution_mode,
        qty=float(position_qty),
        average_entry_price=float(average_entry_price),
        cost_basis=float(cost_basis),
    )
