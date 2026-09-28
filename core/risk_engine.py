from __future__ import annotations

from dataclasses import dataclass, field
import math
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
        current_position_qty: float | None = None,
        account_equity: float | None = None,
        day_start_equity: float | None = None,
        peak_equity: float | None = None,
    ) -> RiskDecision:
        settings = settings or {}
        reasons: List[str] = []
        warnings: List[str] = []

        side = str(side).upper().strip()
        if side not in {"BUY", "SELL"}:
            reasons.append("Order side must be BUY or SELL.")

        if not math.isfinite(qty) or qty <= 0:
            reasons.append("Order quantity must be finite and greater than zero.")
        if not math.isfinite(price) or price <= 0:
            reasons.append("Market price must be finite and greater than zero.")

        notional = max(qty, 0.0) * max(price, 0.0) if math.isfinite(qty) and math.isfinite(price) else 0.0
        if not math.isfinite(notional):
            reasons.append("Estimated order notional must be finite.")
            notional = 0.0

        max_order_notional = float(settings.get("risk_max_order_notional", 1000.0))
        if not math.isfinite(max_order_notional) or max_order_notional <= 0:
            reasons.append("risk_max_order_notional must be finite and greater than zero.")
        elif notional > max_order_notional:
            reasons.append(
                f"Estimated order notional {notional:.2f} exceeds configured "
                f"limit {max_order_notional:.2f}."
            )

        if current_position_qty is not None and (not math.isfinite(current_position_qty) or current_position_qty < 0):
            reasons.append("Current position quantity must be finite and nonnegative.")
        if side == "SELL" and current_position_qty is not None and math.isfinite(current_position_qty) and qty > max(current_position_qty, 0.0):
            reasons.append(
                f"Sell quantity {qty:.8f} exceeds current position "
                f"{max(current_position_qty, 0.0):.8f}."
            )

        max_position_pct = float(settings.get("risk_max_position_pct", 25.0))
        if account_equity is not None and (not math.isfinite(account_equity) or account_equity <= 0):
            reasons.append("Account equity must be finite and greater than zero.")
        if side == "BUY" and account_equity is not None and math.isfinite(account_equity) and account_equity > 0:
            if not math.isfinite(max_position_pct) or not 0 < max_position_pct <= 100:
                reasons.append("risk_max_position_pct must be between 0 and 100.")
            else:
                max_position_notional = account_equity * (max_position_pct / 100.0)
                if notional > max_position_notional:
                    reasons.append(
                        f"Order notional {notional:.2f} exceeds the configured "
                        f"{max_position_pct:.2f}% per-position equity limit "
                        f"({max_position_notional:.2f})."
                    )

        max_daily_loss_pct = float(settings.get("risk_max_daily_loss_pct", 3.0))
        if day_start_equity is not None and (not math.isfinite(day_start_equity) or day_start_equity <= 0):
            reasons.append("Day-start equity must be finite and greater than zero.")
        if not math.isfinite(max_daily_loss_pct) or not 0 < max_daily_loss_pct <= 100:
            reasons.append("risk_max_daily_loss_pct must be between 0 and 100.")
        elif account_equity is not None and day_start_equity is not None and math.isfinite(account_equity) and math.isfinite(day_start_equity) and day_start_equity > 0:
            daily_loss_pct = max(0.0, (day_start_equity - account_equity) / day_start_equity * 100.0)
            if daily_loss_pct >= max_daily_loss_pct:
                reasons.append(
                    f"Daily loss {daily_loss_pct:.2f}% reached configured limit "
                    f"{max_daily_loss_pct:.2f}%."
                )

        max_drawdown_pct = float(settings.get("risk_max_drawdown_pct", 10.0))
        if peak_equity is not None and (not math.isfinite(peak_equity) or peak_equity <= 0):
            reasons.append("Peak equity must be finite and greater than zero.")
        if not math.isfinite(max_drawdown_pct) or not 0 < max_drawdown_pct <= 100:
            reasons.append("risk_max_drawdown_pct must be between 0 and 100.")
        elif account_equity is not None and peak_equity is not None and math.isfinite(account_equity) and math.isfinite(peak_equity) and peak_equity > 0:
            drawdown_pct = max(0.0, (peak_equity - account_equity) / peak_equity * 100.0)
            if drawdown_pct >= max_drawdown_pct:
                reasons.append(
                    f"Account drawdown {drawdown_pct:.2f}% reached configured limit "
                    f"{max_drawdown_pct:.2f}%."
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
            normalized_qty=max(float(qty), 0.0) if math.isfinite(qty) else 0.0,
            estimated_notional=notional,
            reasons=reasons,
            warnings=warnings,
        )


risk_engine = RiskEngine()
