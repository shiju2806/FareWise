# FareWise — Phase C: Event Intelligence + Hotels + Alerts

## Phase C Goal

Transform FareWise from a flight-focused tool into a full travel intelligence platform. Layer destination event data onto the price calendar to explain why prices spike, add hotel search with the same flexible-date and cost-optimization patterns, introduce bundle optimization (flight + hotel combined savings), and build a proactive alert system that notifies travelers of price drops and upcoming booking deadlines.

**Phase C is complete when:** The price calendar shows event markers that explain price spikes, travelers can search and select hotels alongside flights with a combined savings view, and the system proactively sends alerts for price changes and unbooked trips.

**Prerequisites:** Phase A (search, calendar, scoring) and Phase B (policies, savings, approvals) must be complete.

---

## New External APIs

### PredictHQ — Event Intelligence

**What it provides:** Structured event data (conferences, sports, concerts, festivals, public holidays, school breaks, etc.) with attendance estimates and demand impact scores.

**API endpoints we'll use:**

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/events` | Search events by location, date range, category |
| `GET /v1/features` | Demand impact features (accommodation demand, etc.) |

**Auth:** Bearer token via `Authorization: Bearer {access_token}`
**Rate limit:** Varies by plan. Free tier: 1,000 events/day.

**Key parameters for event search:**
```python
params = {
    "location_around.origin": "40.7128,-74.0060",  # lat,lng
    "location_around.offset": "30km",
    "active.gte": "2026-02-14",
    "active.lte": "2026-02-24",
    "category": "conferences,sports,concerts,festivals,performing-arts,community,expos",
    "rank.gte": 50,
    "sort": "-rank",
    "limit": 20
}
```

### Amadeus Hotel API

| Endpoint | Purpose |
|----------|---------|
| `GET /v3/shopping/hotel-offers` | Search hotels with pricing by date |
| `GET /v1/reference-data/locations/hotels/by-city` | Hotels in a city |
| `GET /v1/reference-data/locations/hotels/by-geocode` | Hotels near coordinates |

---

## New Database Tables

### events_cache
```sql
CREATE TABLE events_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    category VARCHAR(50) NOT NULL,
    labels JSONB DEFAULT '[]',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    city VARCHAR(100) NOT NULL,
    country VARCHAR(10),
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    venue_name VARCHAR(300),
    rank INTEGER,
    local_rank INTEGER,
    phq_attendance INTEGER,
    demand_impact JSONB,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_events_city_date ON events_cache(city, start_date, end_date);
CREATE INDEX idx_events_expires ON events_cache(expires_at);
CREATE UNIQUE INDEX idx_events_external ON events_cache(external_id);
```

### hotel_searches
```sql
CREATE TABLE hotel_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_leg_id UUID NOT NULL REFERENCES trip_legs(id) ON DELETE CASCADE,
    city VARCHAR(100) NOT NULL,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    guests INTEGER DEFAULT 1,
    search_params JSONB NOT NULL,
    results_count INTEGER,
    cheapest_rate DECIMAL(10,2),
    most_expensive_rate DECIMAL(10,2),
    cached BOOLEAN DEFAULT false,
    searched_at TIMESTAMPTZ DEFAULT NOW()
);
```

### hotel_options
```sql
CREATE TABLE hotel_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_search_id UUID NOT NULL REFERENCES hotel_searches(id) ON DELETE CASCADE,
    hotel_name VARCHAR(300) NOT NULL,
    hotel_chain VARCHAR(100),
    star_rating DECIMAL(2,1),
    user_rating DECIMAL(2,1),
    address VARCHAR(500),
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    distance_km DECIMAL(5,2),
    nightly_rate DECIMAL(10,2) NOT NULL,
    total_rate DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'CAD',
    room_type VARCHAR(100),
    amenities JSONB DEFAULT '[]',
    cancellation_policy VARCHAR(50),
    is_preferred_vendor BOOLEAN DEFAULT false,
    raw_response JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_hotel_options_search ON hotel_options(hotel_search_id);
CREATE INDEX idx_hotel_options_rate ON hotel_options(nightly_rate);
```

### hotel_selections
```sql
CREATE TABLE hotel_selections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_leg_id UUID NOT NULL REFERENCES trip_legs(id),
    hotel_option_id UUID NOT NULL REFERENCES hotel_options(id),
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    justification_note TEXT,
    selected_at TIMESTAMPTZ DEFAULT NOW()
);
```

### price_watches
```sql
CREATE TABLE price_watches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    watch_type VARCHAR(20) NOT NULL,
    origin VARCHAR(10),
    destination VARCHAR(10),
    target_date DATE NOT NULL,
    flexibility_days INTEGER DEFAULT 3,
    target_price DECIMAL(10,2),
    current_best_price DECIMAL(10,2),
    cabin_class VARCHAR(20) DEFAULT 'economy',
    is_active BOOLEAN DEFAULT true,
    last_checked_at TIMESTAMPTZ,
    alert_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_price_watches_active ON price_watches(is_active, last_checked_at);
CREATE INDEX idx_price_watches_user ON price_watches(user_id);
```

### price_watch_history
```sql
CREATE TABLE price_watch_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    price_watch_id UUID NOT NULL REFERENCES price_watches(id) ON DELETE CASCADE,
    price DECIMAL(10,2) NOT NULL,
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_watch_history ON price_watch_history(price_watch_id, checked_at);
```

---

## Schema Modifications to Existing Tables

### trip_legs — add hotel fields
```sql
ALTER TABLE trip_legs ADD COLUMN needs_hotel BOOLEAN DEFAULT false;
ALTER TABLE trip_legs ADD COLUMN hotel_check_in DATE;
ALTER TABLE trip_legs ADD COLUMN hotel_check_out DATE;
ALTER TABLE trip_legs ADD COLUMN hotel_guests INTEGER DEFAULT 1;
ALTER TABLE trip_legs ADD COLUMN hotel_max_stars DECIMAL(2,1);
```

### savings_reports — add hotel + event data
```sql
ALTER TABLE savings_reports ADD COLUMN hotel_selected_total DECIMAL(10,2);
ALTER TABLE savings_reports ADD COLUMN hotel_cheapest_total DECIMAL(10,2);
ALTER TABLE savings_reports ADD COLUMN bundle_savings DECIMAL(10,2);
ALTER TABLE savings_reports ADD COLUMN events_impacting_price JSONB DEFAULT '[]';
```

### search_logs — add event context
```sql
ALTER TABLE search_logs ADD COLUMN events_during_travel JSONB DEFAULT '[]';
```

---

## API Endpoints

### Events

#### GET /api/events/{city}
Get events for a city within a date range.
Query params: `?date_from=2026-02-14&date_to=2026-02-24&min_rank=50`

Response includes: events list with title, category, labels, dates, venue, rank, attendance, demand impact. Plus a summary with total events, highest impact event, peak impact dates, and recommendation text.

#### GET /api/search/{trip_leg_id}/events
Get events relevant to a specific trip leg (combines destination city + travel dates).

### Hotel Search

#### POST /api/search/{trip_leg_id}/hotels
Search hotels for a trip leg. Supports check-in/check-out dates, guests, max stars, max nightly rate, sort options, and optional near-coordinates for meeting proximity.

Response includes: recommendation, hotel price calendar (±3 days), event warnings, all options with scoring, and area comparison by neighborhood.

#### POST /api/search/{trip_leg_id}/hotels/select
Select a hotel for a trip leg with justification note.

### Bundle Optimization

#### POST /api/search/{trip_leg_id}/bundle
Find optimal flight + hotel combination across flexible dates.

Response includes: top 3 ranked bundles (best value, preferred dates, cheapest), date matrix of all combinations, and event annotations.

### Price Watches

#### POST /api/price-watches
Create a price watch with type (flight/hotel), route, target date, flexibility, and target price.

#### GET /api/price-watches
List user's active watches with current prices, trends, and history.

#### DELETE /api/price-watches/{watch_id}
Cancel a price watch.

### Alerts

#### GET /api/alerts
Get user's recent alerts (triggered price watches + proactive alerts). Types: price_drop, booking_reminder, event_warning.

---

## Service Layer Details

### 1. Event Service (`event_service.py`)

Fetches, caches, and analyzes destination events.

- Cache TTL: 24 hours
- Category filter: conferences, expos, sports, concerts, festivals, performing-arts, community
- Min rank: 40 (filter low-impact events)
- Impact levels: low, medium, high, very_high based on attendance + rank
- Estimated price increase: 5% (low) → 15% (medium) → 30% (high) → 50% (very_high)
- Human-readable summary generated per destination

### 2. PredictHQ Client (`predicthq_client.py`)

Adapter for PredictHQ Events API. Maps raw response to lean Event model. Handles auth, rate limiting, error handling.

### 3. Hotel Search Service (`hotel_service.py`)

Orchestrates hotel search with event-aware pricing.

- Parallel fetch: hotels + events via `asyncio.gather`
- Hotel scoring: 40% price + 25% rating + 20% distance + 15% vendor preference
- Area comparison: group by neighborhood, compute avg/min/max rates
- Event warnings: actionable suggestions when major events overlap travel dates
- Hotel price calendar: ±3 days of nightly rates

### 4. Bundle Optimizer (`bundle_optimizer.py`)

Finds optimal flight + hotel date combinations.

- Builds date matrix: departure dates x return dates = combined totals
- Returns top 3 strategies: best value (per night), preferred dates, cheapest absolute
- Annotates with events explaining price spikes
- Computes savings vs preferred dates for each bundle

### 5. Price Watch Service (`price_watch_service.py`)

Manages price watches and triggers alerts.

- Check interval: every 6 hours
- Default target: 15% below current price if not specified
- Triggers notification when price drops below target
- Logs price history for sparkline trends

### 6. Proactive Alert Service

Generates alerts without user action:
- **Unbooked hotels**: trips within 14 days without hotel booking
- **Event warnings**: high-impact events overlapping upcoming trips
- Runs on scheduled intervals via APScheduler

### 7. Background Scheduler

```python
# APScheduler jobs:
- price_watch_service.check_all_watches    → every 6 hours
- proactive_alert_service.check_unbooked_hotels → daily 9 AM
- proactive_alert_service.check_event_alerts    → daily 10 AM
- event_service.cleanup_expired_cache           → daily 2 AM
```

---

## Frontend Components

### New File Structure (Phase C additions)
```
src/
├── components/
│   ├── events/
│   │   ├── EventBadge.tsx              # Small badge on calendar cells
│   │   ├── EventTooltip.tsx            # Hover detail on calendar
│   │   ├── EventPanel.tsx              # Side panel with full event list
│   │   ├── EventImpactBar.tsx          # Visual impact level indicator
│   │   └── WhyThisPrice.tsx            # Explainer modal/panel
│   ├── hotel/
│   │   ├── HotelSearch.tsx             # Hotel search container
│   │   ├── HotelPriceCalendar.tsx      # Hotel-specific calendar heatmap
│   │   ├── HotelOptionCard.tsx         # Single hotel card
│   │   ├── HotelAreaComparison.tsx     # Neighborhood price comparison
│   │   ├── HotelDetailModal.tsx        # Full hotel details
│   │   └── HotelEventWarning.tsx       # Event impact warning callout
│   ├── bundle/
│   │   ├── BundleOptimizer.tsx         # Combined flight+hotel view
│   │   ├── BundleCard.tsx              # Single bundle option
│   │   ├── BundleDateMatrix.tsx        # Date combination grid
│   │   └── BundleSavingsTag.tsx        # Savings highlight
│   ├── alerts/
│   │   ├── PriceWatchSetup.tsx         # Create price watch form
│   │   ├── PriceWatchList.tsx          # User's active watches
│   │   ├── PriceWatchCard.tsx          # Single watch with sparkline
│   │   ├── PriceSparkline.tsx          # Mini price trend chart
│   │   └── AlertFeed.tsx              # Recent alerts view
│   └── search/
│       └── PriceCalendar.tsx           # UPDATE: add event overlay
├── pages/
│   ├── HotelSearch.tsx
│   ├── BundleView.tsx
│   └── PriceWatches.tsx
├── stores/
│   ├── eventStore.ts
│   ├── hotelStore.ts
│   └── priceWatchStore.ts
```

### Price Calendar — Event Overlay

Phase A calendar enhanced with event markers per cell:
- Event badge with truncated name + category icon
- Impact color: gray (low), amber (medium), orange (high), red (very_high)
- Hover → EventTooltip with full details
- "Why This Price?" button opens explainer panel

**Category icons:** conferences/expos, sports, concerts, performing-arts/festivals, community, public holidays

### Hotel Search

Mirrors flight search pattern: recommendation card, all options, area comparison, hotel price calendar (±3 days), event warnings. Sort by value/price/rating/distance. Filter by max rate, stars, area.

### Hotel Area Comparison

Horizontal bar chart of average nightly rates by neighborhood. Click to filter. Shows option count per area.

### Bundle Optimizer View

Side-by-side cards for top 3 bundles (best value, preferred dates, cheapest). Expandable date matrix heatmap. Event annotations on affected dates.

### Price Watch Components

- **PriceWatchSetup**: "Watch this route" on search results
- **PriceWatchCard**: route, target vs current price, sparkline trend, last checked
- **PriceSparkline**: tiny recharts line (7-14 points), green=down, red=up

### Alert Feed

Dedicated page showing price drops, unbooked hotel reminders, and event warnings with action links.

---

## Updated Sidebar (Phase C)

```
├── New Trip
├── My Trips
├── Approvals          (manager, admin)
├── Price Watches       (NEW)
├── Alerts              (NEW — with unread badge)
├── Dashboard           (placeholder for Phase D)
├── Policies            (admin)
├── ──────────
└── Profile / Settings
```

---

## Integration with Phase B

1. **Savings Report**: includes hotel costs and event context
2. **Narrative Generator**: receives event data ("Hotel prices elevated 40% due to Fashion Week...")
3. **Approval Card**: shows combined flight + hotel total with event annotations
4. **Policy Checks**: now include hotel rules (max rate, star limit, preferred vendors)
5. **Audit Trail**: logs hotel searches, selections, bundle choices, event data shown

---

## Seed Data (Phase C additions)

### Events (cache seed for demo)
1. New York Fashion Week — conferences, Feb 14-19, rank 82, attendance 230K
2. NBA All-Star Weekend — sports, Feb 20-22, NYC, rank 88, attendance 45K
3. Chicago Auto Show — expos, Feb 14-23, Chicago, rank 75, attendance 700K
4. Mobile World Congress — conferences, Mar 2-5, Barcelona, rank 95, attendance 100K
5. SXSW — conferences, Mar 13-22, Austin, rank 90, attendance 300K

### Hotel Policies
1. Max Hotel Rate (Domestic): $250 CAD/night, warn, severity 6
2. Max Hotel Rate (International): $400 CAD/night, warn, severity 7
3. Hotel Star Limit: Max 4 stars for non-VP, warn, severity 5
4. Preferred Hotel Vendors: Marriott, Hilton, IHG — info, severity 2

### Price Watches (demo)
1. Shiju watching YYZ → JFK, target $250, current $305, trending down
2. Shiju watching YYZ → ORD, target $200, current $220, trending flat

---

## Environment Variables (Phase C additions)

```env
PREDICTHQ_ACCESS_TOKEN=your_predicthq_token
PREDICTHQ_BASE_URL=https://api.predicthq.com/v1
EVENT_CACHE_TTL_HOURS=24
EVENT_MIN_RANK=40
EVENT_SEARCH_RADIUS_KM=30
PRICE_WATCH_CHECK_INTERVAL_HOURS=6
HOTEL_SEARCH_CACHE_TTL=1800
SCHEDULER_ENABLED=true
```

---

## Performance Targets

| Operation | Target Latency | Strategy |
|-----------|---------------|----------|
| Event lookup | < 500ms | Cache aggressively (24hr TTL), prefetch on trip creation |
| Hotel search | < 3s | Parallel with event fetch, cache 30min |
| Bundle optimization | < 8s | Limit date matrix size, use cached data |
| Price watch check (per watch) | < 2s | Sequential with small delays |
| Price watch batch (all) | < 30 min | Stagger checks, skip recently checked |

---

## Build Order (Within Phase C)

```
Step 1: Event Intelligence
   - PredictHQ client (adapter)
   - EventService with caching and impact analysis
   - Events API endpoints
   - Frontend: EventBadge + EventTooltip on PriceCalendar
   - WhyThisPrice explainer panel

Step 2: Hotel Search
   - Amadeus Hotel integration (extend adapter)
   - HotelService with scoring and area comparison
   - Hotel search + selection endpoints
   - Frontend: HotelSearch + HotelOptionCard + HotelAreaComparison
   - Hotel event warnings

Step 3: Bundle Optimization
   - BundleOptimizer service
   - Bundle API endpoint
   - Frontend: BundleOptimizer view + BundleCard + BundleDateMatrix
   - Integration with trip submission (include hotel in savings report)

Step 4: Price Watches & Alerts
   - PriceWatch model + service
   - ProactiveAlertService
   - Background scheduler setup (APScheduler)
   - Price watch + alert endpoints
   - Frontend: PriceWatchSetup + PriceWatchCard + AlertFeed

Step 5: Integration & Polish
   - Update savings report to include hotel + events
   - Update narrative generator prompt with event context
   - Update approval card with combined costs
   - Update audit trail with new event types
   - End-to-end testing of full flow
```

---

## Success Criteria for Phase C

Phase C is complete when:

1. Price calendar shows event badges with impact levels for destination cities
2. "Why This Price?" explains what events are driving costs up
3. Travelers can search and select hotels with the same flexible-date calendar pattern
4. Hotel results show area comparison (neighborhood pricing)
5. Event warnings appear on hotel search when major events overlap travel dates
6. Bundle optimizer shows top 3 flight+hotel combinations with savings comparison
7. Date matrix visualizes all possible date combinations with total costs
8. Travelers can set price watches with target prices
9. System sends alerts for price drops, unbooked hotels, and event warnings
10. Savings report and approval card include hotel costs and event context
11. Background scheduler runs price checks and proactive alerts reliably
12. All new data (events, hotels, watches) is captured in the audit trail

---

## Phase Overview

| Phase | Scope | Estimated Effort |
|-------|-------|-----------------|
| **A** | Foundation + Search + UI | ~40% |
| **B** | Policy + Justification + Approvals | ~25% |
| **C** | Events + Hotels + Alerts | ~20% |
| **D** | Analytics + Collaboration + Polish | ~15% |
