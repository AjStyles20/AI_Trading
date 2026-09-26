from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


REQUIRED_AUTONOMOUS_CAPABILITIES = (
    "market_orders",
    "order_status",
    "open_orders",
    "positions",
)


@dataclass(frozen=True)
class ReadinessDecision:
    ready: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


def evaluate_autonomous_readiness(
    *,
    broker_status: Mapping[str, Any],
    account: Mapping[str, Any],
    execution_mode: str,
    asset_type: str,
    unresolved_order: bool,
    ledger_position_qty: float,
    broker_position_qty: float | None,
    risk_approved: bool,
    broker_validation_ok: bool,
) -> ReadinessDecision:
    """Return a deterministic, fail-closed autonomous-session readiness verdict."""
    reasons: list[str] = []
    warnings: list[str] = []

    if execution_mode not in {"paper", "live"}:
        reasons.append(f"Unsupported execution mode: {execution_mode}.")

    supported_assets = set(broker_status.get("supported_asset_types") or [])
    if asset_type not in supported_assets:
        reasons.append(f"Broker does not support asset type: {asset_type}.")

    if not bool(broker_status.get("configured", False)):
        reasons.append("Broker is not configured.")

    if execution_mode == "live" and not bool(broker_status.get("supports_live", False)):
        reasons.append("Broker does not support live execution.")

    if not bool(account.get("can_trade", False)):
        reasons.append("Broker account is not trade-enabled for this execution mode.")

    capabilities = broker_status.get("capabilities") or {}
    missing = [
        capability
        for capability in REQUIRED_AUTONOMOUS_CAPABILITIES
        if not bool(capabilities.get(capability, False))
    ]
    if missing:
        reasons.append(
            "Broker lacks required autonomous capabilities: " + ", ".join(missing) + "."
        )

    if unresolved_order:
        reasons.append("An unresolved prior order exists in this trading scope.")

    if not risk_approved:
        reasons.append("Central risk preflight did not approve the reference order.")

    if not broker_validation_ok:
        reasons.append("Broker validation did not approve the reference order.")

    if broker_position_qty is None:
        reasons.append("Broker position quantity is unavailable.")
    else:
        tolerance = max(1e-8, abs(float(ledger_position_qty)) * 1e-6)
        if abs(float(broker_position_qty) - float(ledger_position_qty)) > tolerance:
            reasons.append(
                "Position drift detected between confirmed-fill ledger "
                f"({float(ledger_position_qty):.8f}) and broker "
                f"({float(broker_position_qty):.8f})."
            )

    if not bool(capabilities.get("cancellation", False)):
        warnings.append(
            "Broker does not advertise order cancellation; autonomous operation "
            "must rely on final-state reconciliation for submitted orders."
        )

    return ReadinessDecision(
        ready=not reasons,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )
