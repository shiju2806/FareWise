"""Recommendation engine configuration — single source for all thresholds."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PolicyBudgets:
    """Per-cabin one-way budget limits (CAD)."""
    economy: int = 800
    premium_economy: int = 1500
    business: int = 3500
    first: int = 6000

    def get(self, cabin_class: str) -> int | None:
        return getattr(self, cabin_class.replace(" ", "_"), None)


@dataclass(frozen=True)
class JustificationThresholds:
    """When to trigger a justification nudge."""
    min_savings_amount: float = 100.0    # $100 over cheapest
    min_savings_percent: float = 10.0    # 10% over cheapest


@dataclass(frozen=True)
class CabinDowngradeThresholds:
    """When to suggest a cabin downgrade."""
    min_savings_amount: float = 200.0
    min_savings_percent: float = 15.0


@dataclass(frozen=True)
class AlternativeThresholds:
    """Minimum savings to show an alternative per layer."""
    layer1_min_savings: float = 50.0     # same-day swaps
    layer1_routing_min_savings: float = 100.0  # same airline, different routing
    layer2_min_savings: float = 100.0    # date shifts
    layer3_min_savings: float = 200.0    # different month
    layer4_min_savings: float = 200.0    # cabin/routing trade-offs


@dataclass(frozen=True)
class CostDriverThresholds:
    """Percentage gaps that indicate a cost driver."""
    airline_gap_pct: float = 10.0    # selected vs cheapest same-date
    date_gap_pct: float = 15.0      # selected-date vs cheapest any-date
    cabin_gap_pct: float = 30.0     # current cabin vs one-down
    route_gap_pct: float = 10.0     # primary vs alternate airport
    stops_gap_pct: float = 20.0     # nonstop vs 1-stop


@dataclass(frozen=True)
class SearchRanges:
    """How far to search for alternatives."""
    trip_window_days: int = 60        # ±60 days for date-shift proposals
    price_calendar_days: int = 7      # ±7 days for price matrix
    max_trip_duration_flex: int = 2    # ±2 days from original trip duration
    min_trip_duration: int = 3         # minimum trip duration in days


@dataclass(frozen=True)
class AlternativeLimits:
    """Maximum alternatives per layer."""
    layer1_max: int = 3    # same-day swaps
    layer1_routing_max: int = 2  # same-airline routing alternatives
    layer2_max: int = 4    # date shifts
    layer3_max: int = 4    # different month / trip-window
    layer4_max: int = 2    # cabin/routing
    total_max: int = 13    # absolute cap


@dataclass(frozen=True)
class TradeOffWeights:
    """Weights for the trade-off resolver scoring.
    Higher = more important. Scale 0-100."""
    policy_compliance: int = 100   # hard filter, not really weighted
    connection_safety: int = 90    # hard filter for < min_layover
    traveler_preference: int = 70  # loyalty airline premium
    net_savings: int = 60          # flight savings minus hotel impact
    disruption: int = 40           # lower disruption = higher score
    sustainability: int = 10       # fewer stops = less emissions

    # Derived values
    min_layover_minutes: int = 90            # below this = unsafe connection
    loyalty_premium_cap: float = 150.0       # max $ value of airline preference


CABIN_DOWNGRADE_MAP: dict[str, str] = {
    "first": "business",
    "business": "premium_economy",
    "premium_economy": "economy",
}

# Corporate day rules for outbound/return
CORPORATE_DAY_RULES = {
    "outbound_weekdays": {4, 5, 6},   # Friday, Saturday, Sunday
    "return_weekdays": {4, 5},         # Friday, Saturday
}


@dataclass(frozen=True)
class LLMParams:
    """Parameters for the advisor LLM call."""
    model_primary: str = "gpt-4o-mini"
    model_fallback: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 800
    temperature: float = 0.1
    json_mode: bool = True


@dataclass(frozen=True)
class AirlinePreferenceScores:
    """Graduated preference scores by airline relationship."""
    user_airline: float = 1.0        # selected/loyalty airline
    same_alliance: float = 0.8      # same alliance partner
    other_full_service: float = 0.5  # full-service, different alliance
    mid_tier: float = 0.3           # regional/leisure carriers
    low_cost: float = 0.15          # ULCCs


@dataclass(frozen=True)
class CurationGuarantees:
    """Slots reserved during curation for diversity."""
    same_alliance_slots: int = 1     # reserve 1 slot for alliance partner


@dataclass(frozen=True)
class RedEyeConfig:
    """Red-eye detection and penalty settings."""
    start_hour: int = 23         # 11pm — departures at or after this are red-eye
    end_hour: int = 6            # 6am — departures before this are red-eye
    penalty_economy: float = 0.7     # disruption multiplier for economy/premium_economy
    penalty_business: float = 0.4    # disruption multiplier for business/first
    hard_filter_cabins: tuple = ("business", "first")  # hard-exclude red-eyes for these cabins

    def is_red_eye(self, departure_time: str) -> bool:
        """Check if departure falls in the red-eye window (23:00-05:59)."""
        if not departure_time or len(departure_time) < 16:
            return False
        try:
            hour = int(departure_time[11:13])
            return hour >= self.start_hour or hour < self.end_hour
        except (ValueError, IndexError):
            return False

    def is_excluded(self, departure_time: str, cabin_class: str) -> bool:
        """Hard-exclude red-eye departures for business/first cabin."""
        if cabin_class not in self.hard_filter_cabins:
            return False
        return self.is_red_eye(departure_time)


@dataclass(frozen=True)
class RecommendationConfig:
    """Top-level config aggregating all sub-configs."""
    policy_budgets: PolicyBudgets = field(default_factory=PolicyBudgets)
    justification: JustificationThresholds = field(default_factory=JustificationThresholds)
    cabin_downgrade: CabinDowngradeThresholds = field(default_factory=CabinDowngradeThresholds)
    alternatives: AlternativeThresholds = field(default_factory=AlternativeThresholds)
    cost_drivers: CostDriverThresholds = field(default_factory=CostDriverThresholds)
    search_ranges: SearchRanges = field(default_factory=SearchRanges)
    limits: AlternativeLimits = field(default_factory=AlternativeLimits)
    trade_offs: TradeOffWeights = field(default_factory=TradeOffWeights)
    llm: LLMParams = field(default_factory=LLMParams)
    airline_preferences: AirlinePreferenceScores = field(default_factory=AirlinePreferenceScores)
    curation: CurationGuarantees = field(default_factory=CurationGuarantees)
    red_eye: RedEyeConfig = field(default_factory=RedEyeConfig)


# Singleton — import this everywhere
recommendation_config = RecommendationConfig()
