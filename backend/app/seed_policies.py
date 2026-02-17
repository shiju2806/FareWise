"""Seed default travel policies for Phase B."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.policy import Policy


SEED_POLICIES = [
    {
        "name": "Max Domestic Economy Fare",
        "description": "Economy flights within Canada/US must not exceed $600 USD",
        "rule_type": "max_price",
        "conditions": {"route_type": "domestic", "cabin": "economy"},
        "threshold": {"amount": 600, "currency": "USD"},
        "action": "warn",
        "severity": 7,
    },
    {
        "name": "Max International Economy Fare",
        "description": "International economy flights must not exceed $1,850 USD",
        "rule_type": "max_price",
        "conditions": {"route_type": "international", "cabin": "economy"},
        "threshold": {"amount": 1850, "currency": "USD"},
        "action": "warn",
        "severity": 8,
    },
    {
        "name": "Max Domestic Business Fare",
        "description": "Business class flights must not exceed $2,000 USD per leg",
        "rule_type": "max_price",
        "conditions": {"route_type": "domestic", "cabin": "business"},
        "threshold": {"amount": 2000, "currency": "USD"},
        "action": "warn",
        "severity": 9,
    },
    {
        "name": "Cabin Restriction",
        "description": "Economy only for flights 6 hours or less",
        "rule_type": "cabin_restriction",
        "conditions": {"max_flight_hours": 6},
        "threshold": {"allowed_cabins": ["economy"]},
        "action": "warn",
        "severity": 6,
    },
    {
        "name": "Advance Booking Requirement",
        "description": "All flights must be booked at least 7 days in advance",
        "rule_type": "advance_booking",
        "conditions": {},
        "threshold": {"min_days": 7},
        "action": "warn",
        "severity": 5,
    },
    {
        "name": "Preferred Airlines",
        "description": "Air Canada (AC) and WestJet (WS) are preferred carriers",
        "rule_type": "preferred_airline",
        "conditions": {},
        "threshold": {"airlines": ["AC", "WS"]},
        "action": "info",
        "severity": 3,
    },
    {
        "name": "Maximum Stops",
        "description": "Flights should not have more than 2 stops",
        "rule_type": "max_stops",
        "conditions": {},
        "threshold": {"max_stops": 2},
        "action": "warn",
        "severity": 4,
    },
    {
        "name": "Business Class Leg Limit",
        "description": "Limit number of legs booked in business class per trip",
        "rule_type": "cabin_class_count",
        "conditions": {"target_cabin": "business"},
        "threshold": {
            "max_legs": 1,
            "suggest_2": "premium_economy",
            "suggest_4": "economy",
        },
        "action": "warn",
        "severity": 7,
    },
    {
        "name": "Auto-Approve Threshold",
        "description": "Trips under $370 USD total qualify for auto-approval",
        "rule_type": "approval_threshold",
        "conditions": {},
        "threshold": {"amount": 370, "currency": "USD"},
        "action": "info",
        "severity": 1,
    },
]


async def seed():
    async with async_session_factory() as db:
        # Check if policies already exist
        result = await db.execute(select(Policy))
        existing = result.scalars().all()
        if existing:
            print(f"Policies already exist ({len(existing)}), skipping seed.")
            return

        for p_data in SEED_POLICIES:
            policy = Policy(**p_data)
            db.add(policy)

        await db.commit()
        print(f"Seeded {len(SEED_POLICIES)} policies.")


if __name__ == "__main__":
    asyncio.run(seed())
