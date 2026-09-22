from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RiskDecision:
    approved: bool
    normalized_qty: float
    estimated_notional: float
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "normalized_qty": self.normalized_qty,
            "estimated_notional": self.estimated_notional,
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


class RiskEngine:
    """Central pre-trade guardrail.

    This is deliberately conservative. Broker validation still runs afterwards;
    risk approval never implies that a broker will accept an order.
    """

    def evaluate_order(
        self,
        *,
        side: str,
        qty: float,
        price: float,
        execution_mode: str,
        settings: Dict[str, Any] | None = None,
    ) -> RiskDecision:
        settings = settings or {}
        reasons: List[str] = []
        warnings: List[str] = []

        side = str(side).upper().strip()
        if side not in {"BUY", "SELL"}:
            reasons.append("Order side must be BUY or SELL.")

        if qty <= 0:
            reasons.append("Order quantity must be greater than zero.")
        if price <= 0:
            reasons.append("Market price must be greater than zero.")

        notional = max(qty, 0.0) * max(price, 0.0)

        max_order_notional = float(settings.get("risk_max_order_notional", 1000.0))
        if max_order_notional <= 0:
            reasons.append("risk_max_order_notional must be greater than zero.")
        elif notional > max_order_notional:
            reasons.append(
                f"Estimated order notional {notional:.2f} exceeds configured "
                f"limit {max_order_notional:.2f}."
            )

        if execution_mode == "live":
            live_enabled = bool(settings.get("risk_live_trading_enabled", False))
            if not live_enabled:
                reasons.append(
                    "Live trading is locked. Explicitly enable "
                    "risk_live_trading_enabled before submitting live orders."
                )

        return RiskDecision(
            approved=not reasons,
            normalized_qty=max(float(qty), 0.0),
            estimated_notional=notional,
            reasons=reasons,
            warnings=warnings,
        )


risk_engine = RiskEngine()
