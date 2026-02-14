# FareWise — Phase A: Foundation + Core Search Experience

## Project Overview

FareWise is a corporate travel cost optimization platform that helps travelers find the most cost-effective flights while providing managers with transparent audit trails for approval decisions. The system proactively suggests alternate dates, routes, and airports to save money, and auto-generates human-readable justification narratives.

**Phase A Goal:** Build the complete backend foundation and core search experience. A traveler can log in, describe a trip in natural language (or use structured form), see a price calendar heatmap with ±7 day flexibility, explore alternate routes/airports, and use a "What If" cost↔convenience slider to explore tradeoffs interactively.

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | React 18 + TypeScript + Vite | Modern, fast build tooling |
| UI Library | shadcn/ui + Tailwind CSS | Clean, accessible components with minimal custom CSS |
| State Management | Zustand | Lightweight, no boilerplate |
| Backend | Python 3.11 + FastAPI | Async-native, excellent for API orchestration |
| Database | PostgreSQL 15 | Relational integrity for audit trails, JSONB for flexible fields |
| Migrations | Alembic | Industry standard for SQLAlchemy |
| ORM | SQLAlchemy 2.0 (async) | Type-safe, async session support |
| Cache | Redis | Price caching, session storage |
| Flight Data | Amadeus Self-Service API | Free tier for development, clean REST API |
| NLP Parsing | Anthropic Claude API (claude-sonnet-4-5-20250929) | Natural language trip description → structured JSON |
| Auth | JWT (python-jose) + bcrypt | Simple role-based auth, no external provider needed |
| HTTP Client | httpx (async) | For all external API calls |

---

## Project Structure

```
farewise/
├── CLAUDE.md
├── docker-compose.yml                 # PostgreSQL + Redis
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/                  # Migration files
│   ├── app/
│   │   ├── main.py                    # FastAPI app factory, CORS, lifespan
│   │   ├── config.py                  # Settings via pydantic-settings (.env)
│   │   ├── database.py                # Async engine, session factory
│   │   ├── dependencies.py            # Dependency injection (get_db, get_current_user)
│   │   ├── models/                    # SQLAlchemy models
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── trip.py
│   │   │   ├── search_log.py
│   │   │   └── policy.py
│   │   ├── schemas/                   # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── trip.py
│   │   │   ├── search.py
│   │   │   └── flight.py
│   │   ├── routers/                   # API endpoints
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── trips.py
│   │   │   ├── search.py
│   │   │   └── users.py
│   │   ├── services/                  # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── amadeus_client.py      # Amadeus API adapter
│   │   │   ├── search_orchestrator.py # Coordinates search across providers
│   │   │   ├── nlp_parser.py          # Claude API for natural language parsing
│   │   │   ├── airport_service.py     # Nearby airport logic
│   │   │   ├── price_aggregator.py    # Combines & ranks results
│   │   │   ├── cache_service.py       # Redis caching layer
│   │   │   └── scoring_engine.py      # Cost↔convenience scoring
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── airports.py            # Airport/city data (IATA codes, coordinates)
│   └── tests/
│       ├── conftest.py
│       ├── test_search.py
│       ├── test_nlp_parser.py
│       └── test_scoring.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── public/
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                       # API client layer
│       │   ├── client.ts              # Axios instance with auth interceptor
│       │   ├── auth.ts
│       │   ├── trips.ts
│       │   └── search.ts
│       ├── stores/                    # Zustand stores
│       │   ├── authStore.ts
│       │   ├── tripStore.ts
│       │   └── searchStore.ts
│       ├── components/
│       │   ├── layout/
│       │   │   ├── AppShell.tsx
│       │   │   ├── Sidebar.tsx
│       │   │   └── Header.tsx
│       │   ├── auth/
│       │   │   ├── LoginForm.tsx
│       │   │   └── ProtectedRoute.tsx
│       │   ├── trip/
│       │   │   ├── TripBuilder.tsx
│       │   │   ├── NaturalLanguageInput.tsx
│       │   │   ├── StructuredTripForm.tsx
│       │   │   ├── LegCard.tsx
│       │   │   └── LegList.tsx
│       │   ├── search/
│       │   │   ├── SearchResults.tsx
│       │   │   ├── PriceCalendar.tsx
│       │   │   ├── CalendarCell.tsx
│       │   │   ├── RouteComparator.tsx
│       │   │   ├── FlightOptionCard.tsx
│       │   │   ├── WhatIfSlider.tsx
│       │   │   ├── AirportChip.tsx
│       │   │   └── PriceTrend.tsx
│       │   └── ui/                    # shadcn/ui components
│       ├── pages/
│       │   ├── Dashboard.tsx
│       │   ├── NewTrip.tsx
│       │   ├── TripSearch.tsx
│       │   ├── TripHistory.tsx
│       │   └── Login.tsx
│       ├── hooks/
│       │   ├── useSearch.ts
│       │   ├── useDebounce.ts
│       │   └── usePriceCalendar.ts
│       ├── lib/
│       │   ├── utils.ts
│       │   └── constants.ts
│       └── types/
│           ├── trip.ts
│           ├── flight.ts
│           └── search.ts
```

---

## Database Schema

### users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'traveler',  -- traveler | manager | admin
    department VARCHAR(100),
    manager_id UUID REFERENCES users(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### trips
```sql
CREATE TABLE trips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    traveler_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255),
    status VARCHAR(20) DEFAULT 'draft',             -- draft | searching | submitted | approved | rejected
    natural_language_input TEXT,
    parsed_input JSONB,
    total_estimated_cost DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'CAD',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### trip_legs
```sql
CREATE TABLE trip_legs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    origin_airport VARCHAR(10) NOT NULL,
    origin_city VARCHAR(100) NOT NULL,
    destination_airport VARCHAR(10) NOT NULL,
    destination_city VARCHAR(100) NOT NULL,
    preferred_date DATE NOT NULL,
    flexibility_days INTEGER DEFAULT 3,
    cabin_class VARCHAR(20) DEFAULT 'economy',
    passengers INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trip_legs_trip_id ON trip_legs(trip_id);
```

### search_logs
```sql
CREATE TABLE search_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_leg_id UUID NOT NULL REFERENCES trip_legs(id) ON DELETE CASCADE,
    api_provider VARCHAR(50) NOT NULL,
    search_params JSONB NOT NULL,
    results_count INTEGER,
    cheapest_price DECIMAL(10,2),
    most_expensive_price DECIMAL(10,2),
    cached BOOLEAN DEFAULT false,
    response_time_ms INTEGER,
    searched_at TIMESTAMPTZ DEFAULT NOW()
);
```

### flight_options
```sql
CREATE TABLE flight_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_log_id UUID NOT NULL REFERENCES search_logs(id) ON DELETE CASCADE,
    airline_code VARCHAR(10) NOT NULL,
    airline_name VARCHAR(100) NOT NULL,
    flight_numbers VARCHAR(100) NOT NULL,
    origin_airport VARCHAR(10) NOT NULL,
    destination_airport VARCHAR(10) NOT NULL,
    departure_time TIMESTAMPTZ NOT NULL,
    arrival_time TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER NOT NULL,
    stops INTEGER DEFAULT 0,
    stop_airports VARCHAR(100),
    price DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'CAD',
    cabin_class VARCHAR(20),
    seats_remaining INTEGER,
    is_alternate_airport BOOLEAN DEFAULT false,
    is_alternate_date BOOLEAN DEFAULT false,
    raw_response JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_flight_options_search_id ON flight_options(search_log_id);
CREATE INDEX idx_flight_options_price ON flight_options(price);
```

### selections (schema for Phase B, created now)
```sql
CREATE TABLE selections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_leg_id UUID NOT NULL REFERENCES trip_legs(id),
    flight_option_id UUID NOT NULL REFERENCES flight_options(id),
    justification_note TEXT,
    slider_position DECIMAL(3,2),
    selected_at TIMESTAMPTZ DEFAULT NOW()
);
```

### policies (schema only in Phase A, logic in Phase B)
```sql
CREATE TABLE policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    conditions JSONB NOT NULL,
    threshold JSONB NOT NULL,
    action VARCHAR(20) DEFAULT 'warn',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### nearby_airports (reference table)
```sql
CREATE TABLE nearby_airports (
    id SERIAL PRIMARY KEY,
    city_name VARCHAR(100) NOT NULL,
    airport_iata VARCHAR(10) NOT NULL,
    airport_name VARCHAR(200) NOT NULL,
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    is_primary BOOLEAN DEFAULT false,
    metro_area VARCHAR(100)
);
```

---

## API Endpoints

### Auth

#### POST /api/auth/register
```json
// Request
{
    "email": "shiju@company.com",
    "password": "securepassword",
    "first_name": "Shiju",
    "last_name": "M",
    "role": "traveler",
    "department": "Finance"
}

// Response 201
{
    "id": "uuid",
    "email": "shiju@company.com",
    "first_name": "Shiju",
    "last_name": "M",
    "role": "traveler",
    "token": "jwt_token_here"
}
```

#### POST /api/auth/login
```json
// Request
{ "email": "shiju@company.com", "password": "securepassword" }

// Response 200
{
    "token": "jwt_token_here",
    "user": { "id": "uuid", "email": "...", "first_name": "...", "role": "..." }
}
```

### Trip Builder

#### POST /api/trips
Create a new trip (draft status).
```json
// Request
{
    "natural_language_input": "Toronto to NYC next Tuesday, back Friday, then Chicago Monday through Wednesday"
}

// Response 201
{
    "id": "trip_uuid",
    "title": "Toronto → New York → Chicago → Toronto",
    "status": "draft",
    "natural_language_input": "Toronto to NYC next Tuesday...",
    "parsed_input": {
        "confidence": 0.95,
        "legs": [
            {
                "sequence": 1,
                "origin_city": "Toronto",
                "origin_airport": "YYZ",
                "destination_city": "New York",
                "destination_airport": "JFK",
                "preferred_date": "2026-02-17",
                "flexibility_days": 3,
                "cabin_class": "economy"
            }
        ],
        "interpretation_notes": "Inferred return leg Chicago → Toronto. Dates resolved relative to today."
    },
    "legs": []
}
```

#### POST /api/trips/structured
Create trip from structured form input (fallback).

#### GET /api/trips
List user's trips. Query params: `?status=draft&page=1&limit=20`

#### GET /api/trips/{trip_id}
Get full trip details with legs.

#### PUT /api/trips/{trip_id}/legs
Update trip legs (add, remove, reorder, modify).

#### DELETE /api/trips/{trip_id}
Delete a draft trip.

### Search

#### POST /api/search/{trip_leg_id}
Execute search for a single leg. Returns flight options across flexible dates and alternate airports.

Response includes:
- `price_calendar` — date-indexed min/max prices with option counts
- `recommendation` — best balanced option with score
- `alternatives` — grouped into cheaper_dates, alternate_airports, different_routing
- `all_options` — full list sorted by score
- `metadata` — airports searched, dates searched, timing info

#### GET /api/search/{trip_leg_id}/options?date=2026-02-17&sort=price
Get all flight options for a specific date (when user clicks a calendar cell).

#### POST /api/search/{trip_leg_id}/score
Recalculate scores based on slider position.
```json
// Request
{ "cost_weight": 0.3, "time_weight": 0.5, "stops_weight": 0.2 }

// Response 200
{ "recommendation": {}, "rescored_options": [] }
```

### Users

#### GET /api/users/me
Current user profile.

#### GET /api/users/me/frequent-routes
Frequent routes for the current user.

---

## Service Layer Details

### 1. NLP Parser Service (`nlp_parser.py`)

Uses Claude API (`claude-sonnet-4-5-20250929`) to parse natural language trip descriptions into structured trip data.

- `temperature: 0`, `max_tokens: 1000`
- Retry logic (max 2 retries)
- If confidence < 0.7, flag for user verification via structured form
- No caching — each parse is unique

### 2. Amadeus Client (`amadeus_client.py`)

Adapter pattern wrapping the Amadeus Self-Service API.

**Endpoints:**
| Amadeus Endpoint | Use |
|-----------------|-----|
| `GET /v2/shopping/flight-offers` | Primary flight search |
| `GET /v1/shopping/flight-dates` | Cheapest date search for calendar |
| `GET /v1/reference-data/locations` | Airport/city autocomplete |
| `GET /v1/reference-data/locations/airports` | Nearest airports by geo |

- OAuth2 client credentials auth (token cached, refresh proactively)
- Rate limit: 10 req/s via `asyncio.Semaphore`
- Exponential backoff on 429
- Map Amadeus JSON to lean `FlightOffer` dataclass
- Parse ISO 8601 durations to minutes

### 3. Search Orchestrator (`search_orchestrator.py`)

Coordinates full search flow for a single leg:
1. Look up nearby airports for origin and destination
2. Build search matrix (dates × airport combos)
3. Execute Amadeus calls in parallel via `asyncio.gather`
4. Aggregate results
5. Run scoring engine
6. Generate recommendation + grouped alternatives
7. Log to search_logs + flight_options tables

Target: < 5 seconds for typical routes.

### 4. Scoring Engine (`scoring_engine.py`)

Ranks flight options with configurable weights:
- `cost` — price relative to cheapest
- `time` — duration relative to shortest
- `stops` — penalty per stop
- `departure` — gaussian curve centered on 9am

**"What If" slider mapping (0=cheapest, 100=convenient):**
```
cost:      0.8 → 0.1
time:      0.1 → 0.5
stops:     0.05 → 0.3
departure: 0.05 → 0.1
```

### 5. Cache Service (`cache_service.py`)

Redis-backed with TTLs:
- Flight prices: 15 min
- Airport data: 24 hours
- Calendar data: 30 min

### 6. Airport Service (`airport_service.py`)

Resolves cities to airports, finds nearby alternatives within radius. Uses nearby_airports table + Amadeus API fallback.

---

## Frontend Component Specifications

### App Shell
Left sidebar (New Trip, My Trips, Dashboard placeholder, Settings placeholder) + header (logo, user info). Clean, minimal. Inter/system fonts.

### Natural Language Input
Hero component — large text area with rotating placeholder examples. Shows parsing state, confidence indicators, and fallback to structured form.

### Structured Trip Form
Per-leg fields: origin/destination (autocomplete), date picker, flexibility pills (±1/3/5/7), cabin class dropdown. Add/remove legs.

### Price Calendar
2-week horizontal calendar (±7 days) with color-coded cells (emerald→amber→red quartiles). Preferred date highlighted with blue ring. Click to expand options.

### Route Comparator
Three collapsible sections: Cheaper Dates, Alternate Airports, Different Routing. Each contains FlightOptionCard components.

### Flight Option Card
Compact card: airline, flight numbers, times, route, duration, stops, price. Badges for savings, alternate airports, low seat counts.

### "What If" Slider
Horizontal slider (0=cheapest, 100=convenient). Debounced 300ms. Re-ranks options in real-time via API call.

### Skeleton Loading
Every data component has a skeleton variant using shadcn/ui Skeleton primitives.

---

## Environment Variables

```env
# Backend (.env)
DATABASE_URL=postgresql+asyncpg://farewise:farewise@localhost:5432/farewise
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-jwt-secret-key-change-in-production
AMADEUS_CLIENT_ID=your_amadeus_client_id
AMADEUS_CLIENT_SECRET=your_amadeus_client_secret
AMADEUS_BASE_URL=https://test.api.amadeus.com
ANTHROPIC_API_KEY=your_anthropic_api_key
CORS_ORIGINS=http://localhost:5173

# Frontend (.env)
VITE_API_BASE_URL=http://localhost:8000/api
```

---

## Docker Compose (Development)

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: farewise
      POSTGRES_USER: farewise
      POSTGRES_PASSWORD: farewise
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

---

## Seed Data Requirements

### Users
1. Traveler: shiju@farewise.com / password123 (role: traveler, dept: Finance, manager: sarah)
2. Manager: sarah@farewise.com / password123 (role: manager, dept: Finance)
3. Admin: admin@farewise.com / password123 (role: admin)

### Nearby Airports
Seed at least these metro areas: Toronto (YYZ, YTZ), New York (JFK, EWR, LGA), Chicago (ORD, MDW), Los Angeles (LAX, SNA, BUR, LGB, ONT), San Francisco (SFO, OAK, SJC), London (LHR, LGW, STN, LTN), Washington DC (IAD, DCA, BWI), Miami (MIA, FLL, PBI), Dallas (DFW, DAL), Houston (IAH, HOU), Boston (BOS, PVD, MHT), Paris (CDG, ORY), Tokyo (NRT, HND), Montreal (YUL), Vancouver (YVR), Calgary (YYC), Ottawa (YOW).

### Policies (schema validation)
1. Max domestic economy: $800 CAD
2. Max international economy: $2500 CAD
3. Advance booking minimum: 7 days

---

## Build Order (Within Phase A)

```
Step 1: Project scaffolding
   - Initialize backend (FastAPI + pyproject.toml + directory structure)
   - Initialize frontend (Vite + React + TypeScript + Tailwind + shadcn)
   - Docker compose for PostgreSQL + Redis
   - Verify both servers start

Step 2: Database + Auth
   - SQLAlchemy models for all tables
   - Alembic initial migration
   - Seed data script
   - Auth endpoints (register, login, JWT middleware)
   - Frontend: Login page + auth store + protected routes

Step 3: Trip Builder
   - NLP parser service (Claude API integration)
   - Trip CRUD endpoints
   - Airport service + nearby airports logic
   - Frontend: NaturalLanguageInput + StructuredTripForm + LegCards

Step 4: Search Engine
   - Amadeus client (adapter pattern)
   - Cache service (Redis)
   - Search orchestrator (parallel search across dates/airports)
   - Scoring engine
   - Search API endpoints
   - Frontend: SearchResults + PriceCalendar + RouteComparator

Step 5: Polish & Integration
   - WhatIfSlider with real-time re-scoring
   - FlightOptionCard selection (save to selections table)
   - Loading skeletons for all components
   - Error states and empty states
   - Trip history page
   - End-to-end testing of full flow
```

---

## Success Criteria for Phase A

Phase A is complete when:

1. A traveler can log in
2. Type a natural language trip description and see it parsed into legs
3. Alternatively, use the structured form to build a multi-city trip
4. Trigger a search for any leg and see a price calendar heatmap
5. See a smart recommendation with grouped alternatives (cheaper dates, alternate airports, different routing)
6. Use the "What If" slider to shift between cost and convenience optimization
7. Select a flight option for a leg
8. All searches are logged in the database
9. The UI is clean, responsive, and uses skeleton loading states
10. The system gracefully handles API errors and edge cases

---

---

## Price Calendar Enhancement (Post-Phase A)

The original Phase A price calendar was a horizontal 7-day strip showing prices for the preferred date ±flexibility_days. This has been upgraded to a full **month-view calendar** with the following improvements:

### Month Calendar Grid
- Full month view (Mon-Sun columns, 5-6 rows) replacing the horizontal date strip
- Previous/next month navigation arrows for browsing across months
- Color-coded cells using price quartiles (green = cheap, amber = average, red = expensive)
- Direct vs connecting flight indicators per day: `●` = direct flights available, `✕` = connecting only
- Visual markers: blue ring for preferred date, green ring for cheapest date
- Past dates greyed out
- Click any date to view flight options for that day
- Lazy-loading: initial search fetches ±flexibility days, remaining month dates fetched on demand
- Each date fetched with max_results=5 (cheapest only) to minimize API calls

### Technical Details
- Backend: `SearchOrchestrator.fetch_month_prices()` — parallel batched Amadeus calls (10/batch)
- Endpoint: `GET /api/search/{leg_id}/calendar?year=YYYY&month=M`
- Caching: 1-hour Redis TTL per month-calendar, reuses per-date flight cache
- Frontend: `MonthCalendar.tsx` with `MonthCalendarCell.tsx`, Zustand store in `priceIntelStore.ts`

---

## Phase Overview

| Phase | Scope | Estimated Effort |
|-------|-------|-----------------|
| **A** | Foundation + Search + UI | ~40% |
| **B** | Policy + Justification + Approvals | ~25% |
| **C** | Events + Hotels + Alerts | ~20% |
| **D** | Analytics + Collaboration + Polish | ~15% |
