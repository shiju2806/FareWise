"""Policy engine — evaluates trips against configurable company policies."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.currency import (
    convert_from_usd,
    convert_to_usd,
    format_price,
    get_currency_for_airport,
    is_domestic_route,
)
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
        threshold_currency = threshold.get("currency", "USD")
        conditions = policy.conditions or {}

        # Check route_type condition — skip if policy targets wrong route type
        route_type = conditions.get("route_type")
        if route_type:
            domestic = is_domestic_route(leg.origin_airport, leg.destination_airport)
            if (route_type == "domestic" and not domestic) or (route_type == "international" and domestic):
                return PolicyCheckResult(
                    policy_id=str(policy.id),
                    policy_name=policy.name,
                    rule_type=policy.rule_type,
                    status="pass",
                    action=policy.action,
                    details=f"Route is {'domestic' if domestic else 'international'}, policy targets {route_type} — skipped",
                    severity=policy.severity,
                    leg_id=str(leg.id),
                )

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

        # Convert both to USD for comparison
        flight_currency = getattr(flight, "currency", None) or "USD"
        # Display in the trip origin's local currency for consistency with frontend
        display_currency = get_currency_for_airport(leg.origin_airport)

        price_usd = Decimal(str(convert_to_usd(float(flight.price), flight_currency)))
        limit_usd = Decimal(str(convert_to_usd(float(max_amount), threshold_currency)))

        # Convert to display currency
        price_local = convert_from_usd(float(price_usd), display_currency)
        limit_local = convert_from_usd(float(limit_usd), display_currency)

        price_display = format_price(price_local, display_currency)
        limit_display = format_price(limit_local, display_currency)

        if price_usd <= limit_usd:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status="pass",
                action=policy.action,
                details=f"{price_display} within limit {limit_display}",
                severity=policy.severity,
                leg_id=str(leg.id),
            )
        else:
            status = "block" if policy.action == "block" else "warn"
            over_usd = float(price_usd - limit_usd)
            over_local = convert_from_usd(over_usd, display_currency)
            over_display = format_price(over_local, display_currency)
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type=policy.rule_type,
                status=status,
                action=policy.action,
                details=f"{price_display} exceeds limit {limit_display} by {over_display}",
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


class PassengerCabinChecker(PolicyChecker):
    """Enforce cabin class restrictions based on passenger count.

    threshold format: {"1": ["economy","premium_economy","business","first"],
                       "2": ["economy","premium_economy"],
                       "4": ["economy"]}
    Keys are passenger count thresholds; values are allowed cabins at that count.
    """

    def check(self, policy, leg, selection, flight) -> PolicyCheckResult:
        allowed_map = policy.threshold or {}
        pax = getattr(leg, "passengers", 1) or 1
        cabin = (getattr(flight, "cabin_class", "economy") or "economy").lower()

        # Find the highest threshold key <= passenger count
        applicable_key = "1"
        for key in sorted(allowed_map.keys(), key=lambda k: int(k)):
            if pax >= int(key):
                applicable_key = key

        allowed_cabins = [c.lower() for c in allowed_map.get(applicable_key, [])]

        if cabin in allowed_cabins:
            return PolicyCheckResult(
                policy_id=str(policy.id),
                policy_name=policy.name,
                rule_type="passenger_cabin",
                status="pass",
                action=policy.action,
                details=f"{cabin} allowed for {pax} passenger(s)",
                severity=policy.severity,
                leg_id=str(leg.id),
            )

        return PolicyCheckResult(
            policy_id=str(policy.id),
            policy_name=policy.name,
            rule_type="passenger_cabin",
            status="warn" if policy.action != "block" else "block",
            action=policy.action,
            details=f"{cabin} not allowed for {pax} passenger(s). Allowed: {', '.join(allowed_cabins)}",
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
    "passenger_cabin": PassengerCabinChecker,
    "approval_threshold": ApprovalThresholdChecker,
    "cabin_class_count": CabinClassCountChecker,
}


def _extract_overage_from_details(details: str) -> float:
    """Extract the numeric overage amount from a details string like 'CA$3,496 exceeds limit CA$2,703 by CA$793'."""
    import re
    m = re.search(r"by\s+[^\d]*([\d,]+)", details)
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


class PolicyEngine:
    """Evaluates all active policies against a trip's selected flights."""

    @staticmethod
    def _consolidate_per_leg_violations(evaluation: PolicyEvaluation, legs: list[TripLeg]) -> None:
        """Merge per-leg max_price blocks/warnings into single trip-level notes.

        Instead of showing "Policy X: CA$3,496 exceeds limit" once per leg,
        produce a single "Policy X: 2 legs exceed fare limit (total overage: CA$2,858)".
        Also consolidates the checks list so the Policy Checks section is clean.
        """
        from collections import defaultdict

        display_currency = get_currency_for_airport(legs[0].origin_airport) if legs else "USD"

        # Group non-pass max_price checks by policy_id
        policy_groups: dict[str, list[PolicyCheckResult]] = defaultdict(list)
        for c in evaluation.checks:
            if c.rule_type == "max_price" and c.status in ("block", "warn"):
                policy_groups[c.policy_id].append(c)

        for policy_id, items in policy_groups.items():
            if len(items) <= 1:
                continue

            total_overage = sum(_extract_overage_from_details(it.details) for it in items)
            overage_display = format_price(total_overage, display_currency)
            consolidated = PolicyCheckResult(
                policy_id=policy_id,
                policy_name=items[0].policy_name,
                rule_type="max_price",
                status=items[0].status,
                action=items[0].action,
                details=f"{len(items)} legs exceed fare limit (total overage: {overage_display})",
                severity=items[0].severity,
            )

            # Replace individual items in checks, blocks, and warnings
            for item in items:
                if item in evaluation.checks:
                    evaluation.checks.remove(item)
                if item in evaluation.blocks:
                    evaluation.blocks.remove(item)
                if item in evaluation.warnings:
                    evaluation.warnings.remove(item)

            evaluation.checks.append(consolidated)
            if consolidated.status == "block":
                evaluation.blocks.append(consolidated)
            elif consolidated.status == "warn":
                evaluation.warnings.append(consolidated)

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
        total_selected_usd = Decimal("0")

        for sel in selections:
            flight = flight_options.get(str(sel.flight_option_id))
            if not flight:
                continue

            flight_currency = getattr(flight, "currency", "CAD") or "CAD"
            total_selected_usd += Decimal(str(convert_to_usd(float(flight.price), flight_currency)))

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

        # Consolidate per-leg max_price violations into single trip-level notes
        self._consolidate_per_leg_violations(evaluation, legs)

        # Check approval_threshold at trip level (compare in USD, display in trip currency)
        trip_currency = get_currency_for_airport(legs[0].origin_airport) if legs else "USD"
        total_trip_local = convert_from_usd(float(total_selected_usd), trip_currency)

        for policy in policies:
            if policy.rule_type == "approval_threshold" and policy.is_active:
                threshold_amount = Decimal(str(policy.threshold.get("amount", 0)))
                t_currency = policy.threshold.get("currency", "USD")
                limit_usd = Decimal(str(convert_to_usd(float(threshold_amount), t_currency)))
                limit_local = convert_from_usd(float(limit_usd), trip_currency)
                total_display = format_price(total_trip_local, trip_currency)
                limit_display = format_price(limit_local, trip_currency)
                if total_selected_usd <= limit_usd:
                    evaluation.checks.append(PolicyCheckResult(
                        policy_id=str(policy.id),
                        policy_name=policy.name,
                        rule_type="approval_threshold",
                        status="pass",
                        action="info",
                        details=f"Total {total_display} qualifies for auto-approval (limit: {limit_display})",
                        severity=policy.severity,
                    ))
                else:
                    evaluation.checks.append(PolicyCheckResult(
                        policy_id=str(policy.id),
                        policy_name=policy.name,
                        rule_type="approval_threshold",
                        status="info",
                        action="info",
                        details=f"Total {total_display} requires manager approval (limit: {limit_display})",
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
