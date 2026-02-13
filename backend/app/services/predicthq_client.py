"""PredictHQ API client — adapter for event intelligence with mock fallback."""

import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Lean event model mapped from PredictHQ response."""
    external_id: str
    title: str
    category: str
    labels: list[str]
    start_date: date
    end_date: date
    city: str
    country: str | None
    latitude: float | None
    longitude: float | None
    venue_name: str | None
    rank: int
    local_rank: int | None
    phq_attendance: int | None


class PredictHQClient:
    """Adapter for PredictHQ Events API."""

    CATEGORIES = "conferences,expos,sports,concerts,festivals,performing-arts,community"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._use_mock = not settings.predicthq_access_token

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.predicthq_base_url,
                timeout=15.0,
            )
        return self._client

    async def search_events(
        self,
        city: str,
        date_from: date,
        date_to: date,
        latitude: float | None = None,
        longitude: float | None = None,
        min_rank: int | None = None,
        limit: int = 20,
    ) -> list[Event]:
        """Search events near a city within a date range."""
        if self._use_mock:
            return self._generate_mock_events(city, date_from, date_to)

        try:
            client = await self._get_client()
            params: dict = {
                "active.gte": date_from.isoformat(),
                "active.lte": date_to.isoformat(),
                "category": self.CATEGORIES,
                "rank.gte": min_rank or settings.event_min_rank,
                "sort": "-rank",
                "limit": limit,
            }

            if latitude and longitude:
                params["location_around.origin"] = f"{latitude},{longitude}"
                params["location_around.offset"] = f"{settings.event_search_radius_km}km"
            else:
                params["q"] = city

            resp = await client.get(
                "/events",
                params=params,
                headers={"Authorization": f"Bearer {settings.predicthq_access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

            events = []
            for r in data.get("results", []):
                geo = r.get("location", [])
                events.append(Event(
                    external_id=r["id"],
                    title=r.get("title", "Unknown Event"),
                    category=r.get("category", "other"),
                    labels=r.get("labels", []),
                    start_date=date.fromisoformat(r["start"][:10]),
                    end_date=date.fromisoformat(r.get("end", r["start"])[:10]),
                    city=city,
                    country=r.get("country", None),
                    latitude=geo[1] if len(geo) == 2 else None,
                    longitude=geo[0] if len(geo) == 2 else None,
                    venue_name=r.get("entities", [{}])[0].get("name") if r.get("entities") else None,
                    rank=r.get("rank", 0),
                    local_rank=r.get("local_rank"),
                    phq_attendance=r.get("phq_attendance"),
                ))
            return events

        except Exception as e:
            logger.error(f"PredictHQ API failed, falling back to mock: {e}")
            return self._generate_mock_events(city, date_from, date_to)

    def _generate_mock_events(
        self, city: str, date_from: date, date_to: date
    ) -> list[Event]:
        """Generate realistic mock events for demo mode."""
        seed_str = f"{city}{date_from.isoformat()}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        # City-specific events database
        city_events = self._get_city_events(city.lower(), date_from, date_to)

        # Add random events if we need more
        categories = ["conferences", "sports", "concerts", "festivals", "expos", "community"]
        event_templates = [
            ("Tech Summit {year}", "conferences", 65, 5000),
            ("Annual Business Forum", "conferences", 55, 2000),
            ("Sports Championship", "sports", 72, 25000),
            ("Music Festival", "concerts", 60, 15000),
            ("Food & Wine Expo", "expos", 48, 8000),
            ("International Trade Fair", "expos", 58, 12000),
            ("Marathon Weekend", "community", 52, 30000),
        ]

        events = list(city_events)

        # Add 1-4 random events within the date range
        total_days = (date_to - date_from).days
        if total_days > 0:
            for _ in range(rng.randint(1, 4)):
                template = rng.choice(event_templates)
                start_offset = rng.randint(0, max(0, total_days - 2))
                duration = rng.randint(1, min(3, total_days - start_offset + 1))
                evt_start = date_from + timedelta(days=start_offset)
                evt_end = evt_start + timedelta(days=duration - 1)

                events.append(Event(
                    external_id=f"mock_{city}_{evt_start.isoformat()}_{rng.randint(1000,9999)}",
                    title=template[0].format(year=date_from.year),
                    category=template[1],
                    labels=[template[1], "business"],
                    start_date=evt_start,
                    end_date=evt_end,
                    city=city,
                    country=None,
                    latitude=None,
                    longitude=None,
                    venue_name=None,
                    rank=template[2] + rng.randint(-10, 10),
                    local_rank=rng.randint(40, 90),
                    phq_attendance=template[3] + rng.randint(-1000, 1000),
                ))

        # Sort by rank descending and deduplicate by external_id and title
        seen_ids = set()
        seen_titles = set()
        unique = []
        for e in sorted(events, key=lambda x: x.rank, reverse=True):
            if e.external_id not in seen_ids and e.title not in seen_titles:
                seen_ids.add(e.external_id)
                seen_titles.add(e.title)
                unique.append(e)
        return unique[:20]

    @staticmethod
    def _get_city_events(
        city: str, date_from: date, date_to: date
    ) -> list[Event]:
        """Return known seed events for popular cities."""
        year = date_from.year
        all_events = [
            Event("phq_nyfw_2026", "New York Fashion Week", "conferences",
                  ["fashion", "business"], date(year, 2, 14), date(year, 2, 19),
                  "New York", "US", 40.7128, -74.0060, "Spring Studios",
                  82, 85, 230000),
            Event("phq_nba_allstar_2026", "NBA All-Star Weekend", "sports",
                  ["basketball", "sports"], date(year, 2, 20), date(year, 2, 22),
                  "New York", "US", 40.7505, -73.9934, "Madison Square Garden",
                  88, 92, 45000),
            Event("phq_chicago_auto_2026", "Chicago Auto Show", "expos",
                  ["automotive", "expos"], date(year, 2, 14), date(year, 2, 23),
                  "Chicago", "US", 41.8741, -87.6298, "McCormick Place",
                  75, 80, 700000),
            Event("phq_mwc_2026", "Mobile World Congress", "conferences",
                  ["technology", "business"], date(year, 3, 2), date(year, 3, 5),
                  "Barcelona", "ES", 41.3545, 2.1287, "Fira Barcelona",
                  95, 98, 100000),
            Event("phq_sxsw_2026", "SXSW", "conferences",
                  ["technology", "music", "film"], date(year, 3, 13), date(year, 3, 22),
                  "Austin", "US", 30.2672, -97.7431, "Austin Convention Center",
                  90, 95, 300000),
            Event("phq_ces_2026", "CES", "expos",
                  ["technology", "consumer-electronics"], date(year, 1, 7), date(year, 1, 10),
                  "Las Vegas", "US", 36.1699, -115.1398, "Las Vegas Convention Center",
                  94, 97, 180000),
            Event("phq_coachella_2026", "Coachella Music Festival", "festivals",
                  ["music", "arts"], date(year, 4, 10), date(year, 4, 19),
                  "Indio", "US", 33.7206, -116.2156, "Empire Polo Club",
                  91, 93, 250000),
            Event("phq_tiff_2026", "Toronto International Film Festival", "festivals",
                  ["film", "arts"], date(year, 9, 4), date(year, 9, 14),
                  "Toronto", "CA", 43.6532, -79.3832, "TIFF Bell Lightbox",
                  85, 90, 480000),
            Event("phq_stampede_2026", "Calgary Stampede", "festivals",
                  ["rodeo", "community"], date(year, 7, 3), date(year, 7, 12),
                  "Calgary", "CA", 51.0375, -114.0518, "Stampede Park",
                  80, 88, 1200000),
        ]

        city_lower = city.lower()
        # Map airport codes and city names to event cities
        city_aliases: dict[str, list[str]] = {
            "new york": ["new york", "nyc", "jfk", "lga", "ewr"],
            "chicago": ["chicago", "ord", "mdw"],
            "barcelona": ["barcelona", "bcn"],
            "austin": ["austin", "aus"],
            "las vegas": ["las vegas", "las", "lvs"],
            "toronto": ["toronto", "yyz"],
            "calgary": ["calgary", "yyc"],
        }

        matched = []
        for evt in all_events:
            evt_city = evt.city.lower()
            aliases = city_aliases.get(evt_city, [evt_city])
            if any(a in city_lower for a in aliases):
                # Check date overlap
                if evt.start_date <= date_to and evt.end_date >= date_from:
                    matched.append(evt)

        return matched

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


predicthq_client = PredictHQClient()
