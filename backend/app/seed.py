"""Seed script for FareWise development database."""

import asyncio

from passlib.context import CryptContext
from sqlalchemy import select, text

from app.database import async_session_factory, engine
from app.models.policy import NearbyAirport, Policy
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Users ──────────────────────────────────────────────────────────────────────

USERS = [
    {
        "email": "shiju@farewise.com",
        "password": "password123",
        "first_name": "Shiju",
        "last_name": "M",
        "role": "traveler",
        "department": "Finance",
    },
    {
        "email": "sarah@farewise.com",
        "password": "password123",
        "first_name": "Sarah",
        "last_name": "Johnson",
        "role": "manager",
        "department": "Finance",
    },
    {
        "email": "admin@farewise.com",
        "password": "password123",
        "first_name": "Admin",
        "last_name": "User",
        "role": "admin",
        "department": "IT",
    },
]

# ── Nearby Airports ────────────────────────────────────────────────────────────

AIRPORTS = [
    # Toronto
    ("Toronto", "YYZ", "Toronto Pearson International", 43.6777, -79.6248, True, "Toronto Metro"),
    ("Toronto", "YTZ", "Billy Bishop Toronto City", 43.6275, -79.3962, False, "Toronto Metro"),
    # New York
    ("New York", "JFK", "John F. Kennedy International", 40.6413, -73.7781, True, "New York Metro"),
    ("New York", "EWR", "Newark Liberty International", 40.6895, -74.1745, False, "New York Metro"),
    ("New York", "LGA", "LaGuardia", 40.7769, -73.8740, False, "New York Metro"),
    # Chicago
    ("Chicago", "ORD", "O'Hare International", 41.9742, -87.9073, True, "Chicago Metro"),
    ("Chicago", "MDW", "Midway International", 41.7868, -87.7522, False, "Chicago Metro"),
    # Los Angeles
    ("Los Angeles", "LAX", "Los Angeles International", 33.9416, -118.4085, True, "Los Angeles Metro"),
    ("Los Angeles", "SNA", "John Wayne Airport", 33.6757, -117.8678, False, "Los Angeles Metro"),
    ("Los Angeles", "BUR", "Hollywood Burbank", 34.1975, -118.3585, False, "Los Angeles Metro"),
    ("Los Angeles", "LGB", "Long Beach", 33.8177, -118.1516, False, "Los Angeles Metro"),
    ("Los Angeles", "ONT", "Ontario International", 34.0560, -117.6012, False, "Los Angeles Metro"),
    # San Francisco
    ("San Francisco", "SFO", "San Francisco International", 37.6213, -122.3790, True, "San Francisco Metro"),
    ("San Francisco", "OAK", "Oakland International", 37.7213, -122.2208, False, "San Francisco Metro"),
    ("San Francisco", "SJC", "San Jose International", 37.3639, -121.9289, False, "San Francisco Metro"),
    # London
    ("London", "LHR", "Heathrow", 51.4700, -0.4543, True, "London Area"),
    ("London", "LGW", "Gatwick", 51.1537, -0.1821, False, "London Area"),
    ("London", "STN", "Stansted", 51.8860, 0.2389, False, "London Area"),
    ("London", "LTN", "Luton", 51.8747, -0.3683, False, "London Area"),
    # Washington DC
    ("Washington DC", "IAD", "Dulles International", 38.9531, -77.4565, True, "Washington DC Metro"),
    ("Washington DC", "DCA", "Ronald Reagan National", 38.8512, -77.0402, False, "Washington DC Metro"),
    ("Washington DC", "BWI", "Baltimore/Washington International", 39.1754, -76.6683, False, "Washington DC Metro"),
    # Miami
    ("Miami", "MIA", "Miami International", 25.7959, -80.2870, True, "Miami Metro"),
    ("Miami", "FLL", "Fort Lauderdale-Hollywood", 26.0726, -80.1527, False, "Miami Metro"),
    ("Miami", "PBI", "Palm Beach International", 26.6832, -80.0956, False, "Miami Metro"),
    # Dallas
    ("Dallas", "DFW", "Dallas/Fort Worth International", 32.8998, -97.0403, True, "Dallas Metro"),
    ("Dallas", "DAL", "Dallas Love Field", 32.8471, -96.8518, False, "Dallas Metro"),
    # Houston
    ("Houston", "IAH", "George Bush Intercontinental", 29.9902, -95.3368, True, "Houston Metro"),
    ("Houston", "HOU", "William P. Hobby", 29.6454, -95.2789, False, "Houston Metro"),
    # Boston
    ("Boston", "BOS", "Logan International", 42.3656, -71.0096, True, "Boston Metro"),
    ("Boston", "PVD", "T.F. Green (Providence)", 41.7267, -71.4204, False, "Boston Metro"),
    ("Boston", "MHT", "Manchester-Boston Regional", 42.9326, -71.4357, False, "Boston Metro"),
    # Paris
    ("Paris", "CDG", "Charles de Gaulle", 49.0097, 2.5479, True, "Paris Area"),
    ("Paris", "ORY", "Orly", 48.7233, 2.3794, False, "Paris Area"),
    # Tokyo
    ("Tokyo", "NRT", "Narita International", 35.7720, 140.3929, True, "Tokyo Area"),
    ("Tokyo", "HND", "Haneda", 35.5494, 139.7798, False, "Tokyo Area"),
    # Canadian cities
    ("Montreal", "YUL", "Montréal-Trudeau International", 45.4706, -73.7408, True, "Montreal Metro"),
    ("Vancouver", "YVR", "Vancouver International", 49.1967, -123.1815, True, "Vancouver Metro"),
    ("Calgary", "YYC", "Calgary International", 51.1215, -114.0076, True, "Calgary Metro"),
    ("Ottawa", "YOW", "Ottawa Macdonald-Cartier", 45.3225, -75.6692, True, "Ottawa Metro"),
]

# ── Policies ───────────────────────────────────────────────────────────────────

POLICIES = [
    {
        "name": "Max Domestic Economy Fare",
        "rule_type": "max_price",
        "conditions": {"route_type": "domestic", "cabin": "economy"},
        "threshold": {"amount": 800, "currency": "CAD"},
        "action": "warn",
    },
    {
        "name": "Max International Economy Fare",
        "rule_type": "max_price",
        "conditions": {"route_type": "international", "cabin": "economy"},
        "threshold": {"amount": 2500, "currency": "CAD"},
        "action": "warn",
    },
    {
        "name": "Advance Booking Minimum",
        "rule_type": "advance_booking",
        "conditions": {},
        "threshold": {"min_days": 7},
        "action": "warn",
    },
]


async def seed():
    async with async_session_factory() as db:
        # Check if already seeded
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none():
            print("Database already seeded. Skipping.")
            return

        # ── Users ──
        manager = User(
            email=USERS[1]["email"],
            password_hash=pwd_context.hash(USERS[1]["password"]),
            first_name=USERS[1]["first_name"],
            last_name=USERS[1]["last_name"],
            role=USERS[1]["role"],
            department=USERS[1]["department"],
        )
        db.add(manager)
        await db.flush()  # get manager.id

        traveler = User(
            email=USERS[0]["email"],
            password_hash=pwd_context.hash(USERS[0]["password"]),
            first_name=USERS[0]["first_name"],
            last_name=USERS[0]["last_name"],
            role=USERS[0]["role"],
            department=USERS[0]["department"],
            manager_id=manager.id,
        )

        admin = User(
            email=USERS[2]["email"],
            password_hash=pwd_context.hash(USERS[2]["password"]),
            first_name=USERS[2]["first_name"],
            last_name=USERS[2]["last_name"],
            role=USERS[2]["role"],
            department=USERS[2]["department"],
        )
        db.add_all([traveler, admin])
        print(f"Created 3 users (traveler: {traveler.email}, manager: {manager.email}, admin: {admin.email})")

        # ── Airports ──
        for city, iata, name, lat, lon, primary, metro in AIRPORTS:
            db.add(NearbyAirport(
                city_name=city,
                airport_iata=iata,
                airport_name=name,
                latitude=lat,
                longitude=lon,
                is_primary=primary,
                metro_area=metro,
            ))
        print(f"Created {len(AIRPORTS)} airport entries across 17 metro areas")

        # ── Policies ──
        for p in POLICIES:
            db.add(Policy(**p))
        print(f"Created {len(POLICIES)} policies")

        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
