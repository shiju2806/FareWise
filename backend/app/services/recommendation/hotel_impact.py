"""Hotel impact calculator — computes net savings after hotel cost changes."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.recommendation.context_assembler import LegContext, TripContext
from app.services.recommendation.hotel_rate_service import HotelRateResult

logger = logging.getLogger(__name__)


@dataclass
class HotelImpact:
    """Hotel cost impact of shifting dates."""
    nights_added: int          # positive = more nights, negative = fewer
    nightly_rate: float | None  # corporate rate (None if unknown)
    cost_change: float | None   # total hotel cost change (None if unknown)
    hotel_chain: str | None
    is_estimated: bool          # True if rate is dynamic/estimated
    status: str                 # "known" | "estimated" | "unknown"

    @property
    def has_impact(self) -> bool:
        return self.nights_added != 0

    def to_dict(self) -> dict:
        return {
            "nights_added": self.nights_added,
            "nightly_rate": round(self.nightly_rate, 2) if self.nightly_rate else None,
            "cost_change": round(self.cost_change, 2) if self.cost_change is not None else None,
            "hotel_chain": self.hotel_chain,
            "is_estimated": self.is_estimated,
            "status": self.status,
        }


@dataclass
class NetSavings:
    """Flight savings minus hotel impact = net savings."""
    flight_savings: float
    hotel_impact: HotelImpact | None
    net_amount: float | None      # None if hotel cost unknown
    net_is_estimated: bool

    @property
    def is_worth_it(self) -> bool:
        """Is the net savings positive (or unknown but flight savings significant)?"""
        if self.net_amount is not None:
            return self.net_amount > 0
        # If hotel impact unknown, flight savings alone must be significant
        return self.flight_savings >= 200

    def to_dict(self) -> dict:
        return {
            "flight_savings": round(self.flight_savings, 2),
            "hotel_impact": self.hotel_impact.to_dict() if self.hotel_impact else None,
            "net_amount": round(self.net_amount, 2) if self.net_amount is not None else None,
            "net_is_estimated": self.net_is_estimated,
        }


class HotelImpactCalculator:
    """Computes hotel cost changes when flight dates shift."""

    def compute_for_date_shift(
        self,
        original_date: str,
        new_date: str,
        leg_context: LegContext,
        is_outbound: bool = True,
    ) -> HotelImpact:
        """Compute hotel impact of shifting a single leg's date.

        For outbound: earlier departure = more hotel nights (arrive earlier)
        For return: later return = more hotel nights (stay longer)
        """
        if not original_date or not new_date:
            return HotelImpact(0, None, None, None, False, "unknown")

        orig = date.fromisoformat(original_date)
        new = date.fromisoformat(new_date)
        day_diff = (new - orig).days

        # Calculate nights change
        if is_outbound:
            # Earlier outbound = more nights (negative day_diff = earlier)
            nights_added = -day_diff
        else:
            # Later return = more nights (positive day_diff = later)
            nights_added = day_diff

        if nights_added == 0:
            return HotelImpact(0, None, 0.0, None, False, "known")

        # Look up hotel rate
        hotel_rate = leg_context.hotel_rate
        if not hotel_rate or not hotel_rate.available:
            return HotelImpact(
                nights_added=nights_added,
                nightly_rate=None,
                cost_change=None,
                hotel_chain=None,
                is_estimated=False,
                status="unknown",
            )

        nightly = float(hotel_rate.nightly_rate) if hotel_rate.nightly_rate else None
        if nightly is None or nightly <= 0:
            # Treat zero/negative rate as unknown (likely data error)
            return HotelImpact(
                nights_added=nights_added,
                nightly_rate=None,
                cost_change=None,
                hotel_chain=hotel_rate.hotel_chain,
                is_estimated=False,
                status="unknown",
            )

        cost_change = nights_added * nightly

        return HotelImpact(
            nights_added=nights_added,
            nightly_rate=nightly,
            cost_change=cost_change,
            hotel_chain=hotel_rate.hotel_chain,
            is_estimated=hotel_rate.is_estimated,
            status="estimated" if hotel_rate.is_estimated else "known",
        )

    def compute_for_trip_window(
        self,
        original_outbound: str,
        original_return: str,
        new_outbound: str,
        new_return: str,
        context: TripContext,
    ) -> HotelImpact:
        """Compute hotel impact for a trip-window shift (both legs move).

        The total hotel nights change is the sum of:
        - Outbound shift: earlier arrival = more nights
        - Return shift: later departure = more nights
        """
        if len(context.legs) < 2:
            return HotelImpact(0, None, 0.0, None, False, "known")

        outbound_leg = context.legs[0]
        return_leg = context.legs[-1]

        # Use destination of outbound leg for hotel rate
        # (that's where the traveler stays)
        hotel_rate = outbound_leg.hotel_rate

        orig_out = date.fromisoformat(original_outbound) if original_outbound else None
        orig_ret = date.fromisoformat(original_return) if original_return else None
        new_out = date.fromisoformat(new_outbound) if new_outbound else None
        new_ret = date.fromisoformat(new_return) if new_return else None

        if not all([orig_out, orig_ret, new_out, new_ret]):
            return HotelImpact(0, None, None, None, False, "unknown")

        # Original stay = return - outbound (nights at destination)
        orig_nights = (orig_ret - orig_out).days
        new_nights = (new_ret - new_out).days
        nights_added = new_nights - orig_nights

        if nights_added == 0:
            return HotelImpact(0, None, 0.0, None, False, "known")

        nightly = float(hotel_rate.nightly_rate) if (hotel_rate and hotel_rate.available and hotel_rate.nightly_rate) else None
        if nightly is None or nightly <= 0:
            return HotelImpact(
                nights_added=nights_added,
                nightly_rate=None,
                cost_change=None,
                hotel_chain=hotel_rate.hotel_chain if hotel_rate else None,
                is_estimated=False,
                status="unknown",
            )

        cost_change = nights_added * nightly

        return HotelImpact(
            nights_added=nights_added,
            nightly_rate=nightly,
            cost_change=cost_change,
            hotel_chain=hotel_rate.hotel_chain,
            is_estimated=hotel_rate.is_estimated,
            status="estimated" if hotel_rate.is_estimated else "known",
        )

    def compute_net_savings(
        self,
        flight_savings: float,
        hotel_impact: HotelImpact | None,
    ) -> NetSavings:
        """Compute net savings = flight savings - hotel cost increase."""
        if hotel_impact is None or not hotel_impact.has_impact:
            return NetSavings(
                flight_savings=flight_savings,
                hotel_impact=hotel_impact,
                net_amount=flight_savings,
                net_is_estimated=False,
            )

        if hotel_impact.cost_change is None:
            # Hotel cost unknown — can't compute net
            return NetSavings(
                flight_savings=flight_savings,
                hotel_impact=hotel_impact,
                net_amount=None,
                net_is_estimated=False,
            )

        net = flight_savings - hotel_impact.cost_change
        return NetSavings(
            flight_savings=flight_savings,
            hotel_impact=hotel_impact,
            net_amount=net,
            net_is_estimated=hotel_impact.is_estimated,
        )


hotel_impact_calculator = HotelImpactCalculator()
