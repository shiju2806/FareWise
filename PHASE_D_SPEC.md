# FareWise — Phase D: Analytics + Collaboration + Gamification + Polish

## Phase D Goal

Elevate FareWise from a functional platform to a production-ready product that leadership loves (analytics prove ROI), travelers enjoy using (gamification drives adoption), and teams coordinate through (collaboration reduces redundant bookings). This phase also handles the fit-and-finish work that separates "works" from "feels professional."

**Phase D is complete when:** Finance/leadership can see company-wide savings dashboards with ROI metrics, travelers have personal savings scores and department leaderboards, teams can detect overlapping travel and coordinate bookings, and the entire application is polished with onboarding, accessibility, dark mode, and comprehensive error handling.

**Prerequisites:** Phases A, B, and C must be complete — the full flight+hotel search, policy engine, approval workflow, event intelligence, and alert system all working.

---

## Module 1: Analytics Dashboard

### Purpose
Prove FareWise's value to leadership with hard numbers. Answer: "How much has this tool saved us?" and "Where are we overspending?"

### New Database Tables

#### analytics_snapshots
```sql
CREATE TABLE analytics_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_type VARCHAR(50) NOT NULL,             -- daily | weekly | monthly | quarterly
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    metrics JSONB NOT NULL,
    -- metrics example:
    -- {
    --   "total_trips": 145,
    --   "total_spend": 187400,
    --   "total_savings_vs_expensive": 94200,
    --   "total_savings_vs_cheapest_not_taken": -12300,
    --   "avg_advance_booking_days": 12.4,
    --   "policy_compliance_rate": 0.94,
    --   "avg_approval_time_hours": 4.2,
    --   "top_routes": [{"route": "YYZ→JFK", "trips": 23, "avg_cost": 340}],
    --   "spend_by_department": {"Finance": 45000, "Engineering": 62000},
    --   "savings_by_department": {"Finance": 22000, "Engineering": 31000},
    --   "event_impact_total": 18500,
    --   "hotel_vs_flight_ratio": 0.62
    -- }
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_snapshots_type_period ON analytics_snapshots(snapshot_type, period_start);
```

#### traveler_scores
```sql
CREATE TABLE traveler_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    period VARCHAR(20) NOT NULL,                    -- monthly | quarterly | yearly | all_time
    period_start DATE NOT NULL,
    total_trips INTEGER DEFAULT 0,
    total_spend DECIMAL(12,2) DEFAULT 0,
    total_savings DECIMAL(12,2) DEFAULT 0,          -- vs most expensive options shown
    smart_savings DECIMAL(12,2) DEFAULT 0,          -- savings from active choices (date shifts, alt airports)
    policy_compliance_rate DECIMAL(4,3) DEFAULT 1.0,
    avg_advance_booking_days DECIMAL(5,1) DEFAULT 0,
    avg_slider_position DECIMAL(4,1) DEFAULT 50,    -- how cost-conscious they are
    score INTEGER DEFAULT 0,                        -- 0-1000 composite score
    rank_in_department INTEGER,
    rank_in_company INTEGER,
    badges JSONB DEFAULT '[]',                      -- earned badges
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scores_user ON traveler_scores(user_id, period);
CREATE INDEX idx_scores_rank ON traveler_scores(period, period_start, score DESC);
```

### API Endpoints

#### GET /api/analytics/overview
Company-wide dashboard (admin and manager roles).
```json
// Query params: ?period=monthly&date=2026-02

// Response 200
{
    "period": { "type": "monthly", "start": "2026-02-01", "end": "2026-02-28" },
    "headline_metrics": {
        "total_trips": 145,
        "total_spend": 187400,
        "total_savings": 94200,
        "savings_percentage": 33.4,
        "policy_compliance_rate": 0.94,
        "avg_approval_time_hours": 4.2,
        "active_travelers": 52
    },
    "trends": {
        "spend_trend": [
            { "month": "2026-01", "spend": 165000, "savings": 82000 },
            { "month": "2026-02", "spend": 187400, "savings": 94200 }
        ],
        "compliance_trend": [
            { "month": "2026-01", "rate": 0.91 },
            { "month": "2026-02", "rate": 0.94 }
        ]
    },
    "spend_by_department": [
        { "department": "Engineering", "spend": 62000, "savings": 31000, "trips": 45 },
        { "department": "Finance", "spend": 45000, "savings": 22000, "trips": 32 },
        { "department": "Sales", "spend": 52000, "savings": 28000, "trips": 41 },
        { "department": "Marketing", "spend": 28400, "savings": 13200, "trips": 27 }
    ],
    "top_routes": [
        { "route": "YYZ → JFK", "trips": 23, "avg_cost": 340, "avg_savings": 145 },
        { "route": "YYZ → ORD", "trips": 18, "avg_cost": 290, "avg_savings": 120 },
        { "route": "YYZ → SFO", "trips": 15, "avg_cost": 520, "avg_savings": 210 }
    ],
    "policy_insights": {
        "most_violated_policy": "Advance Booking (7 days)",
        "violation_count": 12,
        "recommendation": "YYZ→SFO route consistently over policy — consider adjusting limit from $500 to $600"
    },
    "event_impact": {
        "trips_affected_by_events": 28,
        "estimated_event_premium": 18500,
        "highest_impact": "Mobile World Congress — added ~$420/trip in hotel costs"
    }
}
```

#### GET /api/analytics/department/{department}
Department-level drill-down.
```json
// Response 200
{
    "department": "Engineering",
    "period": { "type": "monthly", "start": "2026-02-01", "end": "2026-02-28" },
    "metrics": {
        "total_trips": 45,
        "total_spend": 62000,
        "total_savings": 31000,
        "avg_cost_per_trip": 1378,
        "policy_compliance_rate": 0.93,
        "top_traveler": { "name": "Alex K.", "savings": 4200 }
    },
    "travelers": [
        { "name": "Alex K.", "trips": 8, "spend": 11200, "savings": 4200, "compliance": 1.0 },
        { "name": "Maya R.", "trips": 6, "spend": 8900, "savings": 3100, "compliance": 0.83 }
    ],
    "common_destinations": [
        { "city": "San Francisco", "trips": 12, "avg_cost": 540 },
        { "city": "New York", "trips": 9, "avg_cost": 350 }
    ]
}
```

#### GET /api/analytics/route/{origin}/{destination}
Route-level analytics.
```json
// Response 200
{
    "route": "YYZ → JFK",
    "period": { "type": "quarterly", "start": "2026-01-01", "end": "2026-03-31" },
    "metrics": {
        "total_trips": 23,
        "avg_cost": 340,
        "median_cost": 320,
        "min_cost": 240,
        "max_cost": 580,
        "avg_advance_booking_days": 11.2,
        "avg_savings": 145
    },
    "price_history": [
        { "week": "2026-W01", "avg_price": 310, "min_price": 240 },
        { "week": "2026-W02", "avg_price": 350, "min_price": 280 },
        { "week": "2026-W03", "avg_price": 320, "min_price": 260 }
    ],
    "best_booking_window": {
        "optimal_days_advance": 14,
        "avg_savings_vs_last_minute": 120,
        "best_departure_day": "Tuesday"
    },
    "policy_status": {
        "current_limit": 800,
        "avg_utilization": 0.42,
        "times_exceeded": 0,
        "recommendation": "Limit appropriate — well within bounds"
    }
}
```

#### GET /api/analytics/savings-report
Exportable savings summary for leadership.
```json
// Query params: ?period=quarterly&format=summary

// Response 200
{
    "report": {
        "title": "FareWise Quarterly Savings Report — Q1 2026",
        "generated_at": "2026-03-31T23:59:00Z",
        "executive_summary": "FareWise processed 412 trips in Q1 2026, generating $267,400 in documented savings against the most expensive options travelers were shown. Policy compliance improved from 89% to 94%. Average approval time decreased from 8.1 hours to 4.2 hours.",
        "key_metrics": {
            "trips_processed": 412,
            "total_spend": 534000,
            "documented_savings": 267400,
            "policy_compliance": 0.94,
            "avg_approval_time_hours": 4.2,
            "traveler_adoption": 0.87
        },
        "top_savings_actions": [
            "Date flexibility saved $89,000 (travelers shifting ±2 days)",
            "Alternate airports saved $52,000 (primarily EWR vs JFK)",
            "Hotel event awareness saved $31,000 (avoiding peak event pricing)"
        ],
        "recommendations": [
            "Increase advance booking policy from 7 to 10 days — data shows 10+ day bookings save 18% more",
            "Add Vancouver (YVR) to preferred route list — fastest growing route",
            "Consider adjusting SFO fare limit from $500 to $600 — 40% of trips trigger warnings"
        ]
    }
}
```

#### GET /api/analytics/my-stats
Personal analytics for travelers.
```json
// Response 200
{
    "traveler": "Shiju M.",
    "all_time": {
        "total_trips": 24,
        "total_savings": 8420,
        "smart_choices_count": 18,
        "avg_slider_position": 55,
        "policy_compliance_rate": 0.96,
        "favorite_route": "YYZ → JFK",
        "most_savings_single_trip": 1240
    },
    "current_month": {
        "trips": 3,
        "savings": 1070,
        "rank_in_department": 2,
        "rank_in_company": 8
    },
    "score": {
        "current": 780,
        "previous_month": 720,
        "trend": "up",
        "next_badge_at": 800,
        "next_badge_name": "Road Warrior"
    },
    "badges": [
        { "id": "first_trip", "name": "First Flight", "earned_at": "2026-01-15", "icon": "✈️" },
        { "id": "savings_500", "name": "Penny Pincher", "earned_at": "2026-01-20", "icon": "💰" },
        { "id": "compliance_streak_10", "name": "Policy Pro", "earned_at": "2026-02-01", "icon": "✅" },
        { "id": "savings_5000", "name": "Big Saver", "earned_at": "2026-02-10", "icon": "🏆" }
    ],
    "savings_history": [
        { "month": "2026-01", "savings": 3200, "trips": 4 },
        { "month": "2026-02", "savings": 5220, "trips": 5 }
    ]
}
```

### Analytics Service (`analytics_service.py`)

```python
class AnalyticsService:
    """Aggregates and computes analytics from trip data."""

    async def generate_snapshot(
        self,
        snapshot_type: str,  # daily | weekly | monthly | quarterly
        period_start: date,
        period_end: date
    ) -> AnalyticsSnapshot:
        """
        Compute all metrics for a period. Called by scheduled job.

        Queries:
        - trips joined with savings_reports for spend/savings
        - policy_violations for compliance
        - approvals for approval time
        - selections + flight_options for route analytics
        - hotel_selections for hotel metrics
        - events_cache for event impact
        """
        trips = await self._get_trips_in_period(period_start, period_end)

        metrics = {
            "total_trips": len(trips),
            "total_spend": sum(t.total_estimated_cost or 0 for t in trips),
            "total_savings_vs_expensive": await self._compute_savings_vs_expensive(trips),
            "policy_compliance_rate": await self._compute_compliance_rate(trips),
            "avg_approval_time_hours": await self._compute_avg_approval_time(trips),
            "active_travelers": len(set(t.traveler_id for t in trips)),
            "spend_by_department": await self._compute_spend_by_department(trips),
            "savings_by_department": await self._compute_savings_by_department(trips),
            "top_routes": await self._compute_top_routes(trips),
            "event_impact_total": await self._compute_event_impact(trips),
            "hotel_vs_flight_ratio": await self._compute_hotel_flight_ratio(trips),
        }

        snapshot = AnalyticsSnapshot(
            snapshot_type=snapshot_type,
            period_start=period_start,
            period_end=period_end,
            metrics=metrics
        )

        await self._save_snapshot(snapshot)
        return snapshot

    async def compute_traveler_scores(self, period: str, period_start: date):
        """
        Compute gamification scores for all travelers.

        Score formula (0-1000):
        - Savings efficiency (0-300): smart_savings / total_spend ratio
        - Policy compliance (0-250): compliance_rate × 250
        - Advance booking (0-150): avg_advance_days normalized
        - Cost consciousness (0-150): inverse of avg_slider_position
        - Volume bonus (0-100): log(trips) normalized
        - Badge bonus (0-50): 10 per badge
        """
        travelers = await self._get_active_travelers(period_start)

        scores = []
        for traveler in travelers:
            stats = await self._get_traveler_stats(traveler.id, period, period_start)

            # Savings efficiency: what % of spend did they save?
            savings_ratio = stats.smart_savings / max(stats.total_spend, 1)
            savings_score = min(savings_ratio * 1000, 300)

            # Policy compliance
            compliance_score = stats.policy_compliance_rate * 250

            # Advance booking (14+ days = max, 0 days = 0)
            advance_score = min(stats.avg_advance_booking_days / 14, 1) * 150

            # Cost consciousness (low slider = more cost conscious)
            cost_score = (1 - stats.avg_slider_position / 100) * 150

            # Volume (log scale, max at ~20 trips)
            volume_score = min(math.log(max(stats.total_trips, 1) + 1) / math.log(21), 1) * 100

            # Badges
            badge_score = min(len(stats.badges) * 10, 50)

            total = int(savings_score + compliance_score + advance_score +
                       cost_score + volume_score + badge_score)

            scores.append(TravelerScore(
                user_id=traveler.id,
                period=period,
                period_start=period_start,
                total_trips=stats.total_trips,
                total_spend=stats.total_spend,
                total_savings=stats.total_savings,
                smart_savings=stats.smart_savings,
                policy_compliance_rate=stats.policy_compliance_rate,
                avg_advance_booking_days=stats.avg_advance_booking_days,
                avg_slider_position=stats.avg_slider_position,
                score=total,
                badges=stats.badges
            ))

        # Compute ranks
        scores.sort(key=lambda s: s.score, reverse=True)
        for i, score in enumerate(scores):
            score.rank_in_company = i + 1

        # Department ranks
        dept_groups = defaultdict(list)
        for score in scores:
            dept = await self._get_user_department(score.user_id)
            dept_groups[dept].append(score)
        for dept, dept_scores in dept_groups.items():
            for i, score in enumerate(dept_scores):
                score.rank_in_department = i + 1

        await self._save_scores(scores)
        return scores

    async def check_and_award_badges(self, user_id: UUID):
        """Check if user has earned any new badges."""
        stats = await self._get_traveler_all_time_stats(user_id)
        existing = set(b['id'] for b in stats.badges)

        new_badges = []

        BADGE_DEFINITIONS = [
            {"id": "first_trip", "name": "First Flight", "icon": "✈️",
             "condition": lambda s: s.total_trips >= 1},
            {"id": "savings_500", "name": "Penny Pincher", "icon": "💰",
             "condition": lambda s: s.total_savings >= 500},
            {"id": "savings_5000", "name": "Big Saver", "icon": "🏆",
             "condition": lambda s: s.total_savings >= 5000},
            {"id": "savings_20000", "name": "Savings Champion", "icon": "👑",
             "condition": lambda s: s.total_savings >= 20000},
            {"id": "compliance_streak_5", "name": "Rule Follower", "icon": "📋",
             "condition": lambda s: s.consecutive_compliant_trips >= 5},
            {"id": "compliance_streak_10", "name": "Policy Pro", "icon": "✅",
             "condition": lambda s: s.consecutive_compliant_trips >= 10},
            {"id": "early_bird_5", "name": "Early Bird", "icon": "🐦",
             "condition": lambda s: s.trips_booked_14plus_days >= 5},
            {"id": "trips_10", "name": "Frequent Flyer", "icon": "🌍",
             "condition": lambda s: s.total_trips >= 10},
            {"id": "trips_50", "name": "Road Warrior", "icon": "🛫",
             "condition": lambda s: s.total_trips >= 50},
            {"id": "alt_airport_3", "name": "Airport Explorer", "icon": "🗺️",
             "condition": lambda s: s.alternate_airport_bookings >= 3},
            {"id": "date_flex_5", "name": "Flexible Flyer", "icon": "📅",
             "condition": lambda s: s.date_shifted_bookings >= 5},
            {"id": "bundle_saver", "name": "Bundle Master", "icon": "📦",
             "condition": lambda s: s.bundle_bookings >= 3},
        ]

        for badge in BADGE_DEFINITIONS:
            if badge["id"] not in existing and badge["condition"](stats):
                new_badges.append(badge)

        if new_badges:
            await self._save_badges(user_id, new_badges)
            for badge in new_badges:
                await self.notification_service.create_notification(
                    user_id=user_id,
                    type='badge_earned',
                    title=f'Badge Earned: {badge["icon"]} {badge["name"]}',
                    body=f'Congratulations! You\'ve earned the {badge["name"]} badge.',
                    reference_type='badge',
                    reference_id=badge["id"]
                )

        return new_badges
```

### Analytics Scheduled Jobs

```python
# Add to scheduler setup
scheduler.add_job(
    analytics_service.generate_daily_snapshot,
    'cron', hour=1, minute=0,
    id='daily_analytics'
)

scheduler.add_job(
    analytics_service.compute_all_traveler_scores,
    'cron', hour=2, minute=0,  # after daily snapshot
    id='traveler_scores'
)

scheduler.add_job(
    analytics_service.generate_weekly_snapshot,
    'cron', day_of_week='mon', hour=3,
    id='weekly_analytics'
)

scheduler.add_job(
    analytics_service.generate_monthly_snapshot,
    'cron', day=1, hour=4,
    id='monthly_analytics'
)
```

---

## Module 2: Trip Collaboration

### Purpose
Detect when colleagues are traveling to the same destination around the same time. Enable coordination to share rides, book group hotel rates, or coordinate flight times.

### New Database Tables

#### trip_overlaps
```sql
CREATE TABLE trip_overlaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_a_id UUID NOT NULL REFERENCES trips(id),
    trip_b_id UUID NOT NULL REFERENCES trips(id),
    overlap_city VARCHAR(100) NOT NULL,
    overlap_start DATE NOT NULL,
    overlap_end DATE NOT NULL,
    overlap_days INTEGER NOT NULL,
    notified BOOLEAN DEFAULT false,
    dismissed_by_a BOOLEAN DEFAULT false,
    dismissed_by_b BOOLEAN DEFAULT false,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_overlaps_trips ON trip_overlaps(trip_a_id, trip_b_id);
```

#### group_trips
```sql
CREATE TABLE group_trips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,                     -- "NYC Team Trip — Feb 17-20"
    organizer_id UUID NOT NULL REFERENCES users(id),
    destination_city VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'planning',          -- planning | booked | completed
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE group_trip_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_trip_id UUID NOT NULL REFERENCES group_trips(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    trip_id UUID REFERENCES trips(id),              -- linked individual trip, if exists
    role VARCHAR(20) DEFAULT 'member',              -- organizer | member
    status VARCHAR(20) DEFAULT 'invited',           -- invited | accepted | declined
    joined_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_group_members ON group_trip_members(group_trip_id);
CREATE INDEX idx_group_user ON group_trip_members(user_id);
```

### API Endpoints

#### GET /api/trips/{trip_id}/overlaps
Check for colleagues traveling to the same destination around the same dates.
```json
// Response 200
{
    "overlaps": [
        {
            "id": "overlap_uuid",
            "colleague": {
                "name": "Alex K.",
                "department": "Engineering",
                "trip_title": "New York → Boston"
            },
            "overlap_city": "New York",
            "overlap_dates": { "start": "2026-02-18", "end": "2026-02-20" },
            "overlap_days": 3,
            "potential_savings": {
                "shared_hotel": "Group rate could save ~15% (~$85 per person)",
                "shared_transport": "Shared airport transfer saves ~$40 each"
            }
        },
        {
            "id": "overlap_uuid",
            "colleague": {
                "name": "Maya R.",
                "department": "Engineering",
                "trip_title": "New York"
            },
            "overlap_city": "New York",
            "overlap_dates": { "start": "2026-02-17", "end": "2026-02-19" },
            "overlap_days": 3,
            "potential_savings": {
                "shared_hotel": "Group rate could save ~15% (~$85 per person)",
                "shared_transport": "Consider same flight: AC401 at 08:00"
            }
        }
    ],
    "group_trip_suggestion": {
        "message": "3 people from your company are in New York Feb 17-20. Create a group trip to coordinate?",
        "action": "create_group_trip"
    }
}
```

#### POST /api/group-trips
Create a group trip.
```json
// Request
{
    "name": "NYC Team Visit — Feb 17-20",
    "destination_city": "New York",
    "start_date": "2026-02-17",
    "end_date": "2026-02-20",
    "invite_user_ids": ["alex_uuid", "maya_uuid"],
    "notes": "Client meetings + team dinner"
}

// Response 201
{
    "id": "group_uuid",
    "name": "NYC Team Visit — Feb 17-20",
    "members": [
        { "name": "Shiju M.", "role": "organizer", "status": "accepted" },
        { "name": "Alex K.", "role": "member", "status": "invited" },
        { "name": "Maya R.", "role": "member", "status": "invited" }
    ],
    "notifications_sent": 2
}
```

#### GET /api/group-trips
List user's group trips.

#### GET /api/group-trips/{group_id}
Group trip details with member trips and coordination info.
```json
// Response 200
{
    "id": "group_uuid",
    "name": "NYC Team Visit — Feb 17-20",
    "destination_city": "New York",
    "members": [
        {
            "name": "Shiju M.",
            "role": "organizer",
            "flight": { "airline": "AC401", "departure": "08:00", "price": 320 },
            "hotel": { "name": "Courtyard Midtown", "nightly": 189 }
        },
        {
            "name": "Alex K.",
            "role": "member",
            "flight": { "airline": "AC401", "departure": "08:00", "price": 320 },
            "hotel": null
        },
        {
            "name": "Maya R.",
            "role": "member",
            "flight": null,
            "hotel": null
        }
    ],
    "coordination_tips": [
        "Shiju and Alex are on the same flight (AC401). Consider booking Maya on it too — $320.",
        "Group hotel rate at Courtyard Midtown: $165/night (vs $189 individual) — saves $72 per person over 3 nights.",
        "Shared car from YYZ to Pearson: save ~$30 each vs individual taxis."
    ]
}
```

#### POST /api/group-trips/{group_id}/accept
Accept a group trip invitation.

#### POST /api/group-trips/{group_id}/decline
Decline a group trip invitation.

### Collaboration Service (`collaboration_service.py`)

```python
class CollaborationService:
    """Detects trip overlaps and manages group coordination."""

    async def detect_overlaps(self, trip: Trip) -> list[TripOverlap]:
        """
        Find other trips from same company overlapping in city and dates.

        Logic:
        1. For each leg, find other approved/submitted trips
           with legs to the same destination city
        2. Check date overlap (any days in common)
        3. Exclude already-dismissed overlaps
        4. Compute potential savings estimates
        """
        overlaps = []

        for leg in trip.legs:
            # Find other trips to same destination
            other_legs = await self._find_overlapping_legs(
                destination_city=leg.destination_city,
                date_from=leg.preferred_date - timedelta(days=2),
                date_to=leg.preferred_date + timedelta(days=7),
                exclude_trip_id=trip.id,
                exclude_user_id=trip.traveler_id
            )

            for other_leg in other_legs:
                overlap_start = max(leg.preferred_date, other_leg.preferred_date)
                overlap_end = min(
                    leg.preferred_date + timedelta(days=3),  # estimated stay
                    other_leg.preferred_date + timedelta(days=3)
                )

                if overlap_start <= overlap_end:
                    overlap = TripOverlap(
                        trip_a_id=trip.id,
                        trip_b_id=other_leg.trip_id,
                        overlap_city=leg.destination_city,
                        overlap_start=overlap_start,
                        overlap_end=overlap_end,
                        overlap_days=(overlap_end - overlap_start).days + 1
                    )
                    overlaps.append(overlap)

        # Deduplicate and save
        new_overlaps = await self._save_new_overlaps(overlaps)

        # Notify both travelers if not already notified
        for overlap in new_overlaps:
            await self._notify_overlap(overlap)

        return overlaps

    async def generate_coordination_tips(self, group_trip_id: UUID) -> list[str]:
        """Generate actionable coordination suggestions."""
        group = await self._get_group_with_members(group_trip_id)
        tips = []

        # Check for same flights
        flights = [m.flight for m in group.members if m.flight]
        flight_groups = defaultdict(list)
        for member in group.members:
            if member.flight:
                key = f"{member.flight.airline_code}{member.flight.flight_numbers}"
                flight_groups[key].append(member)

        for flight_key, members in flight_groups.items():
            if len(members) >= 2:
                names = " and ".join(m.name for m in members)
                tips.append(f"{names} are on the same flight ({flight_key}). Share a ride to the airport!")

        # Members without flights — suggest matching
        without_flights = [m for m in group.members if not m.flight]
        popular_flight = max(flight_groups.items(), key=lambda x: len(x[1]), default=None)
        if without_flights and popular_flight:
            for member in without_flights:
                tips.append(
                    f"Consider booking {member.name} on {popular_flight[0]} — "
                    f"{len(popular_flight[1])} others are already on it."
                )

        # Hotel group rate estimate
        hotels = [m.hotel for m in group.members if m.hotel]
        if hotels:
            avg_rate = mean(h.nightly_rate for h in hotels)
            group_discount = 0.15  # assume 15% group discount
            savings_per_person = avg_rate * group_discount * group.nights
            tips.append(
                f"Group hotel rate could save ~${savings_per_person:.0f} per person "
                f"over {group.nights} nights (~15% discount)."
            )

        return tips
```

---

## Module 3: Gamification

### Purpose
Shift traveler psychology from "the company is watching my spending" to "I'm making smart decisions and getting recognized for it."

### Design Philosophy
- **Subtle, not childish** — badges and scores feel more like LinkedIn achievements than mobile game rewards
- **Opt-in visibility** — travelers see their own scores always; leaderboards are opt-in per department
- **Meaningful, not arbitrary** — every badge maps to a real cost-saving behavior

### Badge System

Badges defined in the analytics service above. Visual representation:

```
┌─────────────────────────────────────────────────┐
│  Your FareWise Score                            │
│                                                 │
│       780 / 1000                                │
│  ████████████████████████████████░░░░░░░░░░░░   │
│                                                 │
│  ↑ 60 points from last month                   │
│  Next badge: 🛫 Road Warrior (at 800)           │
│                                                 │
│  Your Badges                                    │
│  ✈️  💰  ✅  🏆                                  │
│  First  Penny Policy Big                        │
│  Flight Pincher Pro   Saver                     │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Leaderboard

```
┌──────────────────────────────────────────────────────────┐
│  Finance Department Leaderboard — February 2026          │
│                                                          │
│  #1  🥇  Sarah J.     920 pts   $6,200 saved            │
│  #2  🥈  Shiju M.     780 pts   $5,220 saved            │
│  #3  🥉  David L.     710 pts   $3,800 saved            │
│  #4      Priya K.     680 pts   $3,200 saved            │
│  #5      Tom W.       590 pts   $2,100 saved            │
│                                                          │
│  Company Average: 620 pts                                │
│                                                          │
│  [View Company Leaderboard]                              │
└──────────────────────────────────────────────────────────┘
```

**Leaderboard rules:**
- Department leaderboard shown by default
- Company-wide leaderboard available but not primary
- Minimum 3 trips in the period to appear on leaderboard
- Anonymous mode: travelers can opt out of leaderboard visibility
- Score breakdown available on hover/click

---

## Module 4: Production Polish

### 4.1 Onboarding

**First-time user tooltip tour (3-5 steps):**

```
Step 1: Natural Language Input
   "Describe your trip naturally — like telling a colleague.
    We'll figure out the rest."
   [Next →]

Step 2: Price Calendar
   "Green dates are cheapest. Tap any date to explore options."
   [Next →]

Step 3: What If Slider
   "Drag to balance cost vs. convenience. We'll re-rank
    options in real-time."
   [Next →]

Step 4: Savings Card (manager view)
   "Each approval includes a savings summary so you can
    approve in seconds."
   [Got it ✓]
```

**Implementation:**
- Use a lightweight tooltip library (react-joyride or custom with Radix Popover)
- Store `onboarding_completed: boolean` in user preferences
- Show only once, dismissable at any step
- "Skip tour" link always available

### 4.2 Dark Mode

**Implementation strategy:**
- Tailwind's `dark:` variant classes
- CSS custom properties for dynamic colors
- Toggle in header (sun/moon icon) + respect system preference
- Store preference in localStorage + user profile

**Color mapping:**
```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f9fafb;
  --bg-card: #ffffff;
  --text-primary: #111827;
  --text-secondary: #6b7280;
  --border: #e5e7eb;
  --accent: #2563eb;
  --success: #059669;
  --warning: #d97706;
  --danger: #dc2626;
}

.dark {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-card: #1e293b;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --border: #334155;
  --accent: #3b82f6;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
}
```

**Critical dark mode elements:**
- Price calendar heatmap needs distinct dark mode colors (emerald/amber/red that work on dark backgrounds)
- Savings card highlight box must remain readable
- Charts (recharts) need dark theme variants
- Event badges need contrast-safe colors

### 4.3 Accessibility (WCAG 2.1 AA)

**Audit checklist:**

| Area | Requirement | Implementation |
|------|------------|----------------|
| Color contrast | 4.5:1 for normal text, 3:1 for large text | Verify all color combinations in both themes |
| Keyboard navigation | All interactive elements reachable via Tab | Focus rings on all buttons, inputs, cards |
| Screen readers | Meaningful ARIA labels | `aria-label` on calendar cells, slider, badges |
| Price calendar | Color not sole indicator | Add price text + trend arrow alongside color coding |
| Charts | Data accessible without visuals | Provide data table alternative for all charts |
| Forms | Labels associated with inputs | `htmlFor` on all labels |
| Error messages | Announced to screen readers | `aria-live="polite"` on error regions |
| Motion | Respect reduced motion preference | `prefers-reduced-motion` media query |
| Focus management | Logical tab order, focus trapping in modals | Radix Dialog handles this natively |
| Images | Alt text on all images | Hotel images, badge icons |

**Focus ring style (consistent across app):**
```css
*:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 4px;
}
```

### 4.4 Micro-animations & Transitions

**Where to add animations:**

| Element | Animation | Duration |
|---------|-----------|----------|
| Price calendar cells | Fade in left-to-right as data loads | 50ms stagger per cell |
| Flight option cards | Slide up with fade | 150ms stagger |
| Savings card | Scale from 0.95 → 1.0 with fade | 300ms ease-out |
| Approval status change | Color morph + checkmark draw | 400ms |
| Notification bell | Subtle bounce on new notification | 300ms spring |
| Slider thumb | Smooth ease on programmatic position changes | 200ms |
| Tab transitions | Fade + slide | 200ms |
| Modal open/close | Scale + fade | 200ms / 150ms |
| Badge earned | Pop with confetti particles | 600ms |
| Score change | Counter animation (number ticks up) | 800ms |

**Implementation:**
- Use CSS transitions for simple effects
- Framer Motion for complex sequences (badge pop, confetti)
- Always respect `prefers-reduced-motion`:
```tsx
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const transition = prefersReducedMotion ? { duration: 0 } : { duration: 0.3, ease: "easeOut" };
```

### 4.5 Comprehensive Error States

Every component needs three states: loading, success, error.

**Error state templates:**

```
Empty state (no data):
┌────────────────────────────────────┐
│         ✈️                          │
│   No trips yet                     │
│   Start by describing your next    │
│   trip above.                      │
└────────────────────────────────────┘

API error:
┌────────────────────────────────────┐
│         ⚠️                          │
│   Couldn't load flight prices      │
│   This is usually temporary.       │
│   [Try Again]                      │
└────────────────────────────────────┘

Network error:
┌────────────────────────────────────┐
│         📡                          │
│   You appear to be offline         │
│   Check your connection and        │
│   try again.                       │
│   [Retry]                          │
└────────────────────────────────────┘

Partial failure:
┌────────────────────────────────────┐
│   ⚠️ Some results may be           │
│   incomplete. Alternate airport    │
│   data is temporarily unavailable. │
│   [Dismiss]                        │
└────────────────────────────────────┘
```

**Error boundary strategy:**
- Global ErrorBoundary at app root → catches catastrophic crashes, shows friendly fallback
- Page-level ErrorBoundary → catches page component errors, shows retry option
- Component-level try/catch → handles API failures gracefully, shows inline error state
- Toast notifications for non-blocking errors (e.g., "Couldn't cache your search — results will still work")

### 4.6 Performance Optimization

| Optimization | Implementation |
|-------------|----------------|
| Code splitting | React.lazy for page components, Suspense with skeleton fallbacks |
| API response caching | React Query (TanStack Query) with stale-while-revalidate |
| Image optimization | Lazy load hotel images, use loading="lazy" attribute |
| Bundle size | Tree shake unused shadcn components, analyze with vite-plugin-visualizer |
| Database queries | Add missing indexes, use EXPLAIN ANALYZE on slow queries |
| Redis pipeline | Batch cache reads in search orchestrator |
| API call deduplication | Deduplicate concurrent identical Amadeus requests |
| Skeleton placeholders | Match exact layout dimensions to prevent layout shift |

**Performance targets (final):**
| Metric | Target |
|--------|--------|
| Time to Interactive (TTI) | < 2 seconds |
| First Contentful Paint (FCP) | < 1 second |
| Largest Contentful Paint (LCP) | < 2.5 seconds |
| Cumulative Layout Shift (CLS) | < 0.1 |
| Full search (API → render) | < 5 seconds |
| Page transitions | < 300ms |
| Slider re-score | < 500ms |

### 4.7 Keyboard Shortcuts

For power users who book frequently.

| Shortcut | Action |
|----------|--------|
| `N` | New trip |
| `S` | Focus search/NLP input |
| `/` | Focus search/NLP input (alternative) |
| `1-9` | Select calendar date (relative to focused week) |
| `←` `→` | Navigate calendar dates |
| `Enter` | Expand selected date / confirm selection |
| `Esc` | Close modal / collapse expanded section |
| `A` | Go to Approvals (manager) |
| `T` | Go to My Trips |
| `?` | Show keyboard shortcuts help |

**Implementation:**
- Global keyboard listener with context awareness (disable when typing in input)
- Small "Keyboard shortcuts" link in footer or `?` icon
- Modal showing all shortcuts when triggered

### 4.8 Persistent Trip Drafts

If a user closes the tab mid-search, their work should survive.

**Implementation:**
- Auto-save trip draft to backend every 30 seconds while editing
- On page load, check for in-progress drafts: "You have an unfinished trip to NYC. [Continue] [Discard]"
- Store current search results in sessionStorage for instant back-navigation
- Slider position persists per leg in the database (already in selections table)

### 4.9 Export & Reporting

**Exportable artifacts:**
- Savings report as PDF (for leadership presentations)
- Trip details as PDF (for expense reports)
- Analytics dashboard as CSV export
- Audit trail as PDF (for compliance)

```python
# PDF generation endpoint
@router.get("/api/reports/savings/{trip_id}/pdf")
async def export_savings_pdf(trip_id: UUID):
    """Generate a PDF savings report for a trip."""
    ...

@router.get("/api/reports/analytics/csv")
async def export_analytics_csv(period: str, date: str):
    """Export analytics data as CSV."""
    ...
```

---

## Frontend Components (Phase D)

### Updated File Structure
```
src/
├── components/
│   ├── analytics/
│   │   ├── AnalyticsDashboard.tsx      # Main analytics view
│   │   ├── HeadlineMetrics.tsx         # Top-level KPI cards
│   │   ├── SpendChart.tsx              # Monthly spend trend (recharts)
│   │   ├── SavingsChart.tsx            # Savings trend (recharts)
│   │   ├── DepartmentBreakdown.tsx     # Spend by department (bar chart)
│   │   ├── RouteAnalytics.tsx          # Top routes table
│   │   ├── ComplianceTrend.tsx         # Compliance rate over time
│   │   ├── PolicyInsights.tsx          # Automated policy recommendations
│   │   └── EventImpactSummary.tsx      # Event-driven cost analysis
│   ├── gamification/
│   │   ├── ScoreCard.tsx               # Personal score display
│   │   ├── BadgeCollection.tsx         # User's earned badges
│   │   ├── BadgePopup.tsx              # New badge celebration modal
│   │   ├── Leaderboard.tsx             # Department/company rankings
│   │   ├── LeaderboardRow.tsx          # Single row in leaderboard
│   │   └── SavingsHistory.tsx          # Monthly savings trend (personal)
│   ├── collaboration/
│   │   ├── OverlapAlert.tsx            # "2 colleagues in NYC" banner
│   │   ├── OverlapCard.tsx             # Individual overlap detail
│   │   ├── GroupTripCreate.tsx         # Create group trip form
│   │   ├── GroupTripDetail.tsx         # Group trip coordination view
│   │   ├── GroupMemberCard.tsx         # Member's booking status
│   │   └── CoordinationTips.tsx        # AI-generated coordination suggestions
│   ├── onboarding/
│   │   ├── OnboardingTour.tsx          # Tooltip tour wrapper
│   │   └── TourStep.tsx               # Individual tooltip step
│   ├── shared/
│   │   ├── ErrorBoundary.tsx           # Error boundary component
│   │   ├── EmptyState.tsx              # Reusable empty state
│   │   ├── ErrorState.tsx              # Reusable error state with retry
│   │   ├── ThemeToggle.tsx             # Dark mode toggle
│   │   ├── KeyboardShortcuts.tsx       # Shortcuts modal
│   │   └── ExportButton.tsx            # PDF/CSV export trigger
│   └── layout/
│       ├── AppShell.tsx                # UPDATE: add theme support + shortcuts
│       └── Sidebar.tsx                 # UPDATE: add Analytics + Collaboration nav
├── pages/
│   ├── ... (Phase A, B, C pages)
│   ├── AnalyticsDashboard.tsx          # Company analytics page
│   ├── DepartmentAnalytics.tsx         # Department drill-down
│   ├── RouteAnalyticsPage.tsx          # Route-level analysis
│   ├── MyStats.tsx                     # Personal score + badges + history
│   ├── Leaderboard.tsx                 # Leaderboard page
│   ├── GroupTrips.tsx                  # Group trip list
│   └── GroupTripDetail.tsx             # Single group trip coordination
├── hooks/
│   ├── ... (existing hooks)
│   ├── useKeyboardShortcuts.ts
│   ├── useTheme.ts
│   ├── useOnboarding.ts
│   └── useAutoSave.ts
├── contexts/
│   └── ThemeContext.tsx                 # Dark mode context provider
```

### Analytics Dashboard Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  Analytics                    [Monthly ▾]  [Feb 2026 ▾]  [📥 CSV]│
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐│
│  │ 145      │ │ $187,400 │ │ $94,200  │ │ 94%                  ││
│  │ trips    │ │ spend    │ │ saved    │ │ policy compliance    ││
│  │ ↑12%     │ │ ↑8%      │ │ ↑15%    │ │ ↑3pp                 ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘│
│                                                                  │
│  ┌────────────────────────────────┐ ┌────────────────────────── ┐│
│  │ Spend & Savings Trend          │ │ Spend by Department      ││
│  │ [line chart: 6 months]         │ │ [horizontal bar chart]   ││
│  │                                │ │                          ││
│  │  📈 ····                       │ │ Eng    ████████ $62K     ││
│  │      ····                      │ │ Sales  ██████  $52K      ││
│  │         ····                   │ │ Finance █████  $45K      ││
│  │                                │ │ Mktg   ███    $28K      ││
│  └────────────────────────────────┘ └──────────────────────────┘│
│                                                                  │
│  ┌────────────────────────────────┐ ┌────────────────────────── ┐│
│  │ Top Routes                     │ │ Policy Insights           ││
│  │                                │ │                          ││
│  │ YYZ→JFK  23 trips  $340 avg   │ │ 💡 YYZ→SFO consistently  ││
│  │ YYZ→ORD  18 trips  $290 avg   │ │    exceeds limit. Adjust ││
│  │ YYZ→SFO  15 trips  $520 avg   │ │    from $500 → $600?    ││
│  │ YYZ→YVR  12 trips  $380 avg   │ │                          ││
│  │                                │ │ 📊 10-day advance booking││
│  │ [View route details →]         │ │    saves 18% more        ││
│  └────────────────────────────────┘ └──────────────────────────┘│
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Personal Stats Page (`MyStats.tsx`)

```
┌──────────────────────────────────────────────────────────────────┐
│  My FareWise Stats                                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Score: 780 / 1000               ↑ 60 from last month    │   │
│  │  ████████████████████████████████░░░░░░░░░░░░             │   │
│  │  Next: 🛫 Road Warrior (at 800)                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │
│  │ 24 trips   │ │ $8,420     │ │ 96%        │ │ #2 in dept │   │
│  │ all time   │ │ saved      │ │ compliant  │ │ this month │   │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘   │
│                                                                  │
│  Badges                                                          │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐     │
│  │ ✈️  │ │ 💰 │ │ ✅ │ │ 🏆 │ │ 🐦 │ │░░░░│ │░░░░│ │░░░░│     │
│  │    │ │    │ │    │ │    │ │    │ │ ?? │ │ ?? │ │ ?? │     │
│  └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘     │
│  First  Penny Policy Big   Early   (locked badges shown gray)   │
│  Flight Pincher Pro  Saver  Bird                                │
│                                                                  │
│  Monthly Savings                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  [bar chart: monthly savings over last 6 months]          │   │
│  │  Jan: $3,200  ████████                                    │   │
│  │  Feb: $5,220  █████████████                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Locked badges:** Shown as grayed-out silhouettes with "?" — gives travelers something to aim for without revealing all conditions (creates curiosity).

### Overlap Alert (`OverlapAlert.tsx`)

Banner shown on trip detail page when overlaps are detected.

```
┌──────────────────────────────────────────────────────────────────┐
│  👥 2 colleagues are also heading to New York around your dates  │
│                                                                  │
│  Alex K. (Engineering) · Feb 18-20                               │
│  Maya R. (Engineering) · Feb 17-19                               │
│                                                                  │
│  [Create Group Trip]  [Dismiss]                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Updated Sidebar (Final)

```
Sidebar:
├── ✨ New Trip
├── ✈️ My Trips
├── 👥 Group Trips         (NEW)
├── 📋 Approvals           (manager, admin)
├── 👁️ Price Watches
├── 🔔 Alerts
├── ──────────
├── 📊 Analytics           (manager, admin — NEW)
├── 🏆 My Stats & Badges   (NEW)
├── 🏅 Leaderboard         (NEW)
├── ──────────
├── ⚙️ Policies            (admin)
├── 🌙 Dark Mode toggle
└── 👤 Profile / Settings
```

---

## Seed Data (Phase D additions)

### Analytics Snapshots
Generate 3 months of synthetic daily/weekly/monthly snapshots with realistic trends:
- Spending gradually increasing (more adoption)
- Savings rate improving month over month
- Compliance trending upward
- Realistic department distributions

### Traveler Scores
Pre-compute scores for all seed users:
- Shiju: 780 (high saver, good compliance)
- Sarah: 920 (manager leading by example)
- Alex: 650 (newer user, building habits)

### Badges
Award appropriate badges to seed users based on their demo trip history.

### Group Trips
One demo group trip: "NYC Team Visit — Feb 17-20" with 3 members at various booking stages.

### Trip Overlaps
Pre-detect overlaps between seed users' demo trips.

---

## Environment Variables (Phase D additions)

```env
# Add to existing .env
ANALYTICS_SNAPSHOT_ENABLED=true
LEADERBOARD_MIN_TRIPS=3
ONBOARDING_ENABLED=true

# Feature flags
FEATURE_DARK_MODE=true
FEATURE_GAMIFICATION=true
FEATURE_COLLABORATION=true
FEATURE_KEYBOARD_SHORTCUTS=true
FEATURE_EXPORT_PDF=true
```

---

## Build Order (Within Phase D)

```
Step 1: Analytics Backend
   - AnalyticsService with snapshot generation
   - Analytics API endpoints (overview, department, route, my-stats)
   - Scheduled jobs for daily/weekly/monthly snapshots
   - Seed historical snapshot data

Step 2: Analytics Dashboard Frontend
   - HeadlineMetrics cards
   - SpendChart + SavingsChart (recharts)
   - DepartmentBreakdown bar chart
   - RouteAnalytics table
   - ComplianceTrend line chart
   - PolicyInsights component
   - CSV export

Step 3: Gamification
   - TravelerScore computation in analytics service
   - Badge checking and awarding logic
   - ScoreCard + BadgeCollection + BadgePopup components
   - Leaderboard page (department + company)
   - MyStats personal page
   - Badge earned notifications

Step 4: Collaboration
   - CollaborationService overlap detection
   - GroupTrip CRUD endpoints
   - Coordination tips generator
   - OverlapAlert banner on trip pages
   - GroupTripCreate + GroupTripDetail pages
   - Group trip notifications

Step 5: Dark Mode & Theming
   - ThemeContext + ThemeToggle
   - CSS custom properties for all colors
   - Update all components with dark: variants
   - Verify contrast ratios in both themes
   - Chart theme variants

Step 6: Accessibility Audit
   - Keyboard navigation audit (every page)
   - Screen reader testing (key flows)
   - ARIA labels on all interactive elements
   - Color contrast verification
   - Focus management in modals
   - Reduced motion support

Step 7: Micro-animations & Transitions
   - Calendar cell load animation
   - Card entrance animations
   - Savings card reveal
   - Badge earned celebration
   - Score counter animation
   - Notification bell bounce
   - Page transitions

Step 8: Error Handling & Resilience
   - Global ErrorBoundary
   - Page-level error boundaries
   - Component-level error states (every data-fetching component)
   - Empty states for all list views
   - Offline detection and messaging
   - API retry logic with exponential backoff
   - Toast notification system

Step 9: Performance & Polish
   - Code splitting with React.lazy
   - TanStack Query for API caching
   - Image lazy loading
   - Bundle analysis and optimization
   - Database query optimization (EXPLAIN ANALYZE)
   - Keyboard shortcuts implementation
   - Persistent draft auto-save
   - Onboarding tooltip tour

Step 10: Export & Final Integration
   - PDF generation for savings reports
   - PDF generation for audit trails
   - CSV export for analytics
   - End-to-end testing of ALL flows
   - Cross-browser testing (Chrome, Firefox, Safari, Edge)
   - Mobile responsive audit
   - Final performance benchmarking
```

---

## Success Criteria for Phase D

Phase D is complete when:

1. Admin/finance can see company-wide analytics with spend trends, savings totals, and compliance rates
2. Department-level and route-level drill-downs are available
3. Policy insights auto-generate recommendations based on data patterns
4. Every traveler has a personal score (0-1000) and can earn 12+ badges
5. Department leaderboards show rankings with opt-out option
6. Badge earned triggers a celebration notification
7. Trip overlaps are auto-detected and surfaced as banners
8. Group trips can be created and coordinated with booking status per member
9. Coordination tips are auto-generated for group trips
10. Dark mode works flawlessly across all pages and components
11. WCAG 2.1 AA accessibility compliance on all critical flows
12. Micro-animations enhance (not slow down) the experience
13. Every component has proper loading, empty, and error states
14. Keyboard shortcuts work for all primary navigation
15. Onboarding tour guides first-time users through key features
16. Savings reports and analytics are exportable as PDF/CSV
17. Performance targets are met (TTI < 2s, search < 5s)
18. The application feels professional, polished, and production-ready

---

## Full Project Success: FareWise is Complete When

All four phases delivered:

| Phase | What It Delivers | Core Value |
|-------|-----------------|------------|
| **A** | Search + Price Calendar + NLP + Slider | Travelers find optimal flights fast |
| **B** | Policy + Savings Narrative + Approvals | Managers approve with confidence in seconds |
| **C** | Events + Hotels + Bundles + Alerts | Intelligence explains and optimizes pricing |
| **D** | Analytics + Gamification + Collaboration + Polish | Leadership sees ROI, travelers are engaged, product feels world-class |

The end result: a corporate travel platform where **travelers want to use it** (it's faster and smarter than alternatives), **managers trust it** (every approval is justified with data), and **leadership champions it** (hard savings numbers, compliance improvement, and employee engagement).
