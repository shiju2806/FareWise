"""Policy engine — evaluates trips against configurable company policies."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy, Selection
from app.models.search_log import FlightOption
from app.models.trip import Trip, TripLeg

logger = logging.getLogger(__name__)


@dataclass
class PolicyCheckResult:
    policy_id: str
    policy_name: str
    rule_type: str
    status: str  # pass | warn | block | info
    action: str  # warn | block | flag_for_review | info
    details: str
    severity: int = 5
    leg_id: str | None = None


@dataclass
class PolicyEvaluation:
    overall_status: str  # compliant | warning | violation
    checks: list[PolicyCheckResult] = field(default_factory=list)
    blocks: list[PolicyCheckResult] = field(default_factory=list)
    warnings: list[PolicyCheckResult] = field(default_factory=list)


class PolicyChecker(ABC):
    @abstractmethod
    def check(
        self,
        policy: Policy,
        leg: TripLeg,
        selection: Selection,
        flight: FlightOption,
    ) -> PolicyCheckResult:
        ...


class MaxPriceChecker(PolicyChecker):
    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        threshold = policy.threshold
        max_amount = Decimal(str(threshold.get("amount", 0)))
        conditions = policy.conditions or {}

        # Check route_type condition
        route_type = conditions.get("route_type")
        if route_type == "domestic":
            # Simple domestic check: same country prefix not reliably determinable from IATA
            # Use as-is for now, applies to all legs
            pass

        # Check cabin condition
        cabin_cond = conditions.get("cabin")
        if cabin_cond and flight.cabin_class and flight.cabin_class.lower() != cabin_cond.lower():
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action=policy.action,
                details=f"Cabin {flight.cabin_class} does not match condition {cabin_cond} — skipped",
                severity=policy.severity,
                leg_id=str(leg.id),
            )

        price = flight.price
        if price <= max_amount:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action=policy.action,
                details=f"${price:.0f} within limit ${max_amount:.0f}",
                severity=policy.severity,
                leg_id=str(leg.id),
            )
        else:
            status = "block" if policy.action == "block" else "warn"
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status=status,
                action=policy.action,
                details=f"${price:.0f} exceeds limit ${max_amount:.0f} by ${price - max_amount:.0f}",
                severity=policy.severity,
                leg_id=str(leg.id),
            )


class AdvanceBookingChecker(PolicyChecker):
    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        min_days = policy.threshold.get("min_days", 7)
        departure = flight.departure_time.date() if hasattr(flight.departure_time, 'date') else leg.preferred_date
        days_ahead = (departure - date.today()).days

        if days_ahead >= min_days:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action=policy.action,
                details=f"Booked {days_ahead} days in advance (min: {min_days})",
                severity=policy.severity,
                leg_id=str(leg.id),
            )
        else:
            status = "block" if policy.action == "block" else "warn"
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status=status,
                action=policy.action,
                details=f"Booked {days_ahead} days in advance (min: {min_days})",
                severity=policy.severity,
                leg_id=str(leg.id),
            )


class CabinRestrictionChecker(PolicyChecker):
    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        conditions = policy.conditions or {}
        max_hours = conditions.get("max_flight_hours", 6)
        allowed_cabins = policy.threshold.get("allowed_cabins", ["economy"])

        flight_hours = flight.duration_minutes / 60
        cabin = (flight.cabin_class or "economy").lower()

        if flight_hours > max_hours or cabin in [c.lower() for c in allowed_cabins]:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action=policy.action,
                details=f"{cabin.title()} class, {flight_hours:.1f}h flight",
                severity=policy.severity,
                leg_id=str(leg.id),
            )
        else:
            status = "block" if policy.action == "block" else "warn"
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status=status,
                action=policy.action,
                details=f"{cabin.title()} class not allowed for flights under {max_hours}h ({flight_hours:.1f}h)",
                severity=policy.severity,
                leg_id=str(leg.id),
            )


class PreferredAirlineChecker(PolicyChecker):
    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        preferred = policy.threshold.get("airlines", [])
        if not preferred:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action="info",
                details="No preferred airlines configured",
                severity=policy.severity,
                leg_id=str(leg.id),
            )

        airline = flight.airline_code.upper()
        if airline in [a.upper() for a in preferred]:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action="info",
                details=f"{flight.airline_name} ({airline}) is preferred",
                severity=policy.severity,
                leg_id=str(leg.id),
            )
        else:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="info",
                action="info",
                details=f"{flight.airline_name} ({airline}) is not in preferred list: {', '.join(preferred)}",
                severity=policy.severity,
                leg_id=str(leg.id),
            )


class MaxStopsChecker(PolicyChecker):
    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        max_stops = policy.threshold.get("max_stops", 2)

        if flight.stops <= max_stops:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action=policy.action,
                details=f"{flight.stops} stop(s) (max: {max_stops})",
                severity=policy.severity,
                leg_id=str(leg.id),
            )
        else:
            status = "block" if policy.action == "block" else "warn"
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status=status,
                action=policy.action,
                details=f"{flight.stops} stop(s) exceeds max {max_stops}",
                severity=policy.severity,
                leg_id=str(leg.id),
            )


class ApprovalThresholdChecker(PolicyChecker):
    """Trip-level check: determines if trip qualifies for auto-approval."""

    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        # This is handled at trip level in evaluate_trip
        return PolicyCheckResult(
            policy_id=str(policy.id),
            policy_name=policy.name,
            rule_type=policy.rule_type,
            status="info",
            action="info",
            details="Checked at trip level",
            severity=policy.severity,
        )


class CabinClassCountChecker(PolicyChecker):
    """Trip-level check: limits how many legs can be booked in a given cabin class."""

    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        # Per-leg stub — real logic is in evaluate_trip
        return PolicyCheckResult(
            policy_id=str(policy.id),
            policy_name=policy.name,
            rule_type=policy.rule_type,
            status="info",
            action="info",
            details="Checked at trip level",
            severity=policy.severity,
        )


CHECKER_MAP: dict[str, type[PolicyChecker]] = {
    "max_price": MaxPriceChecker,
    "advance_booking": AdvanceBookingChecker,
    "cabin_restriction": CabinRestrictionChecker,
    "preferred_airline": PreferredAirlineChecker,
    "max_stops": MaxStopsChecker,
    "approval_threshold": ApprovalThresholdChecker,
    "cabin_class_count": CabinClassCountChecker,
}


class PolicyEngine:
    """Evaluates all active policies against a trip's selected flights."""

    async def evaluate_trip(
        self,
        db: AsyncSession,
        trip: Trip,
        selections: list[Selection],
        flight_options: dict[str, FlightOption],
        legs: list[TripLeg],
        user_role: str = "traveler",
    ) -> PolicyEvaluation:
        # Load active policies
        result = await db.execute(select(Policy).where(Policy.is_active == True))
        policies = result.scalars().all()

        evaluation = PolicyEvaluation(overall_status="compliant")
        total_selected = Decimal("0")

        for sel in selections:
            flight = flight_options.get(str(sel.flight_option_id))
            if not flight:
                continue

            total_selected += flight.price

            # Find the leg for this selection
            leg = next((l for l in legs if l.id == sel.trip_leg_id), None)
            if not leg:
                continue

            for policy in policies:
                # Check exception roles
                exception_roles = policy.exception_roles or []
                if user_role in exception_roles:
                    continue

                checker_cls = CHECKER_MAP.get(policy.rule_type)
                if not checker_cls or policy.rule_type in ("approval_threshold", "cabin_class_count"):
                    continue

                checker = checker_cls()
                check_result = checker.check(policy, leg, sel, flight)
                evaluation.checks.append(check_result)

                if check_result.status == "block":
                    evaluation.blocks.append(check_result)
                elif check_result.status == "warn":
                    evaluation.warnings.append(check_result)

        # Check approval_threshold at trip level
        for policy in policies:
            if policy.rule_type == "approval_threshold" and policy.is_active:
                auto_approve_limit = Decimal(str(policy.threshold.get("amount", 0)))
                if total_selected <= auto_approve_limit:
                    evaluation.checks.append(PolicyCheckResult(
                        policy_id=str(policy.id),
                        policy_name=policy.name,
                        rule_type="approval_threshold",
                        status="pass",
                        action="info",
                        details=f"Total ${total_selected:.0f} qualifies for auto-approval (limit: ${auto_approve_limit:.0f})",
                        severity=policy.severity,
                    ))
                else:
                    evaluation.checks.append(PolicyCheckResult(
                        policy_id=str(policy.id),
                        policy_name=policy.name,
                        rule_type="approval_threshold",
                        status="info",
                        action="info",
                        details=f"Total ${total_selected:.0f} requires manager approval (limit: ${auto_approve_limit:.0f})",
                        severity=policy.severity,
                    ))

        # Check cabin_class_count at trip level
        for policy in policies:
            if policy.rule_type == "cabin_class_count" and policy.is_active:
                target_cabin = (policy.conditions or {}).get("target_cabin", "business")
                max_legs = policy.threshold.get("max_legs", 1)
                suggest_2 = policy.threshold.get("suggest_2", "premium_economy")
                suggest_4 = policy.threshold.get("suggest_4", "economy")

                cabin_legs = 0
                for sel in selections:
                    flight = flight_options.get(str(sel.flight_option_id))
                    if flight and (flight.cabin_class or "").lower() == target_cabin.lower():
                        cabin_legs += 1

                if cabin_legs <= max_legs:
                    evaluation.checks.append(PolicyCheckResult(
                        policy_id=str(policy.id),
                        policy_name=policy.name,
                        rule_type="cabin_class_count",
                        status="pass",
                        action="info",
                        details=f"{cabin_legs} leg(s) in {target_cabin} — within limit of {max_legs}",
                        severity=policy.severity,
                    ))
                elif cabin_legs >= 4:
                    result = PolicyCheckResult(
                        policy_id=str(policy.id),
                        policy_name=policy.name,
                        rule_type="cabin_class_count",
                        status="warn",
                        action="warn",
                        details=f"{cabin_legs} legs in {target_cabin} class. With {cabin_legs} legs, consider booking in {suggest_4} to reduce costs.",
                        severity=policy.severity,
                    )
                    evaluation.checks.append(result)
                    evaluation.warnings.append(result)
                else:
                    result = PolicyCheckResult(
                        policy_id=str(policy.id),
                        policy_name=policy.name,
                        rule_type="cabin_class_count",
                        status="warn",
                        action="warn",
                        details=f"{cabin_legs} legs in {target_cabin} class. Consider booking in {suggest_2} for some legs to reduce costs.",
                        severity=policy.severity,
                    )
                    evaluation.checks.append(result)
                    evaluation.warnings.append(result)

        # Determine overall status
        if evaluation.blocks:
            evaluation.overall_status = "violation"
        elif evaluation.warnings:
            evaluation.overall_status = "warning"
        else:
            evaluation.overall_status = "compliant"

        return evaluation


policy_engine = PolicyEngine()
