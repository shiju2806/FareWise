"""Recommendation engine — modular travel recommendation system.

Modules:
    config              Centralized thresholds and configuration
    context_assembler   Gathers all data the agent needs
    cost_driver_analyzer Identifies why a selection costs what it does
    hotel_rate_service  Corporate hotel rate lookups
    hotel_impact        Computes net savings after hotel cost changes
    flight_alternatives Per-leg and trip-window alternative generation
    trade_off_resolver  Ranks alternatives by weighted trade-off scoring
    advisor             Single LLM call for reasoning and narrative
    audience_adapter    Formats output for traveler / manager / audit views

Pipeline:
    ContextAssembler → FlightAlternativesGenerator → TradeOffResolver
    → TravelAdvisor → AudienceAdapter.for_traveler/for_manager/for_audit
"""
