"""Event service — fetches, caches, and analyzes destination events."""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.events import EventCache
from app.services.predicthq_client import predicthq_client, Event

logger = logging.getLogger(__name__)

# Impact thresholds based on attendance + rank
IMPACT_LEVELS = {
    "very_high": {"min_rank": 85, "min_attendance": 50000, "price_increase": 0.50},
    "high": {"min_rank": 70, "min_attendance": 20000, "price_increase": 0.30},
    "medium": {"min_rank": 55, "min_attendance": 5000, "price_increase": 0.15},
    "low": {"min_rank": 0, "min_attendance": 0, "price_increase": 0.05},
}

CATEGORY_ICONS = {
    "conferences": "briefcase",
    "expos": "briefcase",
    "sports": "trophy",
    "concerts": "music",
    "performing-arts": "theater",
    "festivals": "theater",
    "community": "users",
    "public-holidays": "flag",
}


def _classify_impact(rank: int, attendance: int | None) -> str:
    """Classify event impact level based on rank and attendance."""
    att = attendance or 0
    if rank >= 85 or att >= 50000:
        return "very_high"
    if rank >= 70 or att >= 20000:
        return "high"
    if rank >= 55 or att >= 5000:
        return "medium"
    return "low"


def _estimated_price_increase(impact_level: str) -> float:
    """Return estimated price increase percentage for an impact level."""
    return IMPACT_LEVELS.get(impact_level, IMPACT_LEVELS["low"])["price_increase"]


class EventService:
    """Fetches, caches, and analyzes destination events."""

    async def get_events(
        self,
        db: AsyncSession,
        city: str,
        date_from: date,
        date_to: date,
        min_rank: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[dict]:
        """Get events for a city/date range. Uses cache if available."""
        # Check cache first
        cached = await self._get_cached_events(db, city, date_from, date_to)
        if cached:
            logger.info(f"Cache hit: {len(cached)} events for {city}")
            return cached

        # Fetch from PredictHQ
        events = await predicthq_client.search_events(
            city=city,
            date_from=date_from,
            date_to=date_to,
            latitude=latitude,
            longitude=longitude,
            min_rank=min_rank or settings.event_min_rank,
        )

        # Cache results
        await self._cache_events(db, events, city)

        # Convert to response format
        return [self._event_to_dict(e) for e in events]

    async def get_events_for_leg(
        self,
        db: AsyncSession,
        destination_city: str,
        preferred_date: date,
        flexibility_days: int = 3,
        price_calendar: dict | None = None,
    ) -> dict:
        """Get events relevant to a trip leg with impact analysis.

        Args:
            price_calendar: Optional dict mapping date strings to
                {min_price, ...} for cross-validating recommendations.
        """
        date_from = preferred_date - timedelta(days=flexibility_days)
        date_to = preferred_date + timedelta(days=flexibility_days)

        events = await self.get_events(db, destination_city, date_from, date_to)

        # Build per-date event map for calendar overlay
        date_events: dict[str, list[dict]] = {}
        for event in events:
            evt_start = date.fromisoformat(event["start_date"])
            evt_end = date.fromisoformat(event["end_date"])
            d = max(evt_start, date_from)
            while d <= min(evt_end, date_to):
                ds = d.isoformat()
                if ds not in date_events:
                    date_events[ds] = []
                date_events[ds].append({
                    "title": event["title"],
                    "category": event["category"],
                    "icon": event["icon"],
                    "impact_level": event["impact_level"],
                    "price_increase_pct": event["price_increase_pct"],
                    "attendance": event["attendance"],
                })
                d += timedelta(days=1)

        # Summary
        highest_impact = max(events, key=lambda e: e["rank"]) if events else None
        peak_dates = sorted(date_events.keys(), key=lambda d: len(date_events[d]), reverse=True)

        summary = {
            "total_events": len(events),
            "highest_impact_event": highest_impact["title"] if highest_impact else None,
            "peak_impact_dates": peak_dates[:3],
            "recommendation": self._generate_recommendation(
                events, preferred_date, date_events, price_calendar
            ),
        }

        return {
            "events": events,
            "date_events": date_events,
            "summary": summary,
        }

    def _generate_recommendation(
        self,
        events: list[dict],
        preferred_date: date,
        date_events: dict[str, list[dict]],
        price_calendar: dict | None = None,
    ) -> str | None:
        """Generate a recommendation, cross-validated against actual prices when available."""
        if not events:
            return None

        pref_str = preferred_date.isoformat()
        pref_events = date_events.get(pref_str, [])

        # Get actual price data if available
        cal_dates = price_calendar or {}
        pref_price = cal_dates.get(pref_str, {}).get("min_price")

        high_impact = [e for e in pref_events if e["impact_level"] in ("high", "very_high")]
        if high_impact:
            names = ", ".join(e["title"] for e in high_impact[:2])

            # Find a lighter date (fewer/lower-impact events)
            lighter_dates = [
                d for d in sorted(date_events.keys())
                if d != pref_str and all(
                    e["impact_level"] in ("low", "medium") for e in date_events[d]
                )
            ]

            # Cross-validate against actual prices
            if pref_price and lighter_dates and cal_dates:
                alt_date = lighter_dates[0]
                alt_price = cal_dates.get(alt_date, {}).get("min_price")

                if alt_price and alt_price > 0:
                    if pref_price <= alt_price:
                        # Event date is actually cheaper — don't suggest alternatives
                        return (
                            f"Major event on {pref_str}: {names}. "
                            f"Despite higher demand, current fares (${int(pref_price)}) "
                            f"are competitive with nearby dates."
                        )
                    else:
                        # Event date IS more expensive — use actual difference
                        pct_diff = round((pref_price - alt_price) / alt_price * 100)
                        return (
                            f"Major event on {pref_str}: {names}. "
                            f"Fares are ~{pct_diff}% higher (${int(pref_price)} vs "
                            f"${int(alt_price)} on {alt_date})."
                        )

            # No price data — use estimate but qualify it
            max_increase = max(e["price_increase_pct"] for e in high_impact)
            alt = f" Consider {lighter_dates[0]} instead." if lighter_dates else ""
            return (
                f"Major event on {pref_str}: {names}. "
                f"Prices may be ~{int(max_increase*100)}% higher (estimate).{alt}"
            )

        if pref_events:
            return f"{len(pref_events)} event(s) on your preferred date may slightly affect prices."

        return None

    def _event_to_dict(self, event: Event | EventCache) -> dict:
        """Convert Event or EventCache to response dict."""
        if isinstance(event, Event):
            rank = event.rank
            attendance = event.phq_attendance
            return {
                "external_id": event.external_id,
                "title": event.title,
                "category": event.category,
                "labels": event.labels,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat(),
                "city": event.city,
                "country": event.country,
                "latitude": event.latitude,
                "longitude": event.longitude,
                "venue_name": event.venue_name,
                "rank": rank,
                "local_rank": event.local_rank,
                "attendance": attendance,
                "icon": CATEGORY_ICONS.get(event.category, "calendar"),
                "impact_level": _classify_impact(rank, attendance),
                "price_increase_pct": _estimated_price_increase(
                    _classify_impact(rank, attendance)
                ),
            }
        # EventCache model
        rank = event.rank or 0
        attendance = event.phq_attendance
        return {
            "external_id": event.external_id,
            "title": event.title,
            "category": event.category,
            "labels": event.labels or [],
            "start_date": event.start_date.isoformat(),
            "end_date": event.end_date.isoformat(),
            "city": event.city,
            "country": event.country,
            "latitude": float(event.latitude) if event.latitude else None,
            "longitude": float(event.longitude) if event.longitude else None,
            "venue_name": event.venue_name,
            "rank": rank,
            "local_rank": event.local_rank,
            "attendance": attendance,
            "icon": CATEGORY_ICONS.get(event.category, "calendar"),
            "impact_level": _classify_impact(rank, attendance),
            "price_increase_pct": _estimated_price_increase(
                _classify_impact(rank, attendance)
            ),
        }

    async def _get_cached_events(
        self, db: AsyncSession, city: str, date_from: date, date_to: date
    ) -> list[dict] | None:
        """Get events from cache if not expired."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(EventCache).where(
                EventCache.city.ilike(f"%{city}%"),
                EventCache.start_date <= date_to,
                EventCache.end_date >= date_from,
                EventCache.expires_at > now,
            )
        )
        cached = result.scalars().all()
        if not cached:
            return None
        return [self._event_to_dict(c) for c in cached]

    async def _cache_events(
        self, db: AsyncSession, events: list[Event], city: str
    ) -> None:
        """Cache events in the database."""
        ttl = timedelta(hours=settings.event_cache_ttl_hours)
        expires_at = datetime.now(timezone.utc) + ttl

        for event in events:
            # Upsert by external_id
            existing = await db.execute(
                select(EventCache).where(EventCache.external_id == event.external_id)
            )
            cached = existing.scalar_one_or_none()

            if cached:
                cached.title = event.title
                cached.rank = event.rank
                cached.phq_attendance = event.phq_attendance
                cached.expires_at = expires_at
                cached.fetched_at = datetime.now(timezone.utc)
            else:
                db.add(EventCache(
                    external_id=event.external_id,
                    title=event.title,
                    category=event.category,
                    labels=event.labels,
                    start_date=event.start_date,
                    end_date=event.end_date,
                    city=city,
                    country=event.country,
                    latitude=event.latitude,
                    longitude=event.longitude,
                    venue_name=event.venue_name,
                    rank=event.rank,
                    local_rank=event.local_rank,
                    phq_attendance=event.phq_attendance,
                    expires_at=expires_at,
                ))

        try:
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to cache events: {e}")
            await db.rollback()

    async def cleanup_expired_cache(self, db: AsyncSession) -> int:
        """Remove expired events from cache."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            delete(EventCache).where(EventCache.expires_at <= now)
        )
        await db.commit()
        return result.rowcount


event_service = EventService()
