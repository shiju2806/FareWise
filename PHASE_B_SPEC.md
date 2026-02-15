# FareWise — Phase B: Policy Engine + Justification + Approvals

## Phase B Goal

Build the business logic layer that transforms FareWise from a search tool into a compliance and approval platform. When a traveler selects flights, the system evaluates them against configurable company policies, auto-generates a human-readable savings narrative using Claude API, and routes the trip through a manager approval workflow with one-click actions.

**Phase B is complete when:** A traveler selects flights → system checks policies → generates a savings report card with narrative → submits for approval → manager sees the request in their dashboard → approves/rejects/comments → traveler is notified of the decision. Full audit trail is captured throughout.

**Prerequisite:** Phase A must be complete — trip builder, search, price calendar, scoring engine, and flight selection all working.

---

## New Database Tables

### approvals
```sql
CREATE TABLE approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    approver_id UUID NOT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'pending',          -- pending | approved | rejected | changes_requested | escalated
    comments TEXT,
    decided_at TIMESTAMPTZ,
    escalated_from UUID REFERENCES approvals(id),
    escalation_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approvals_trip ON approvals(trip_id);
CREATE INDEX idx_approvals_approver ON approvals(approver_id, status);
```

### savings_reports
```sql
CREATE TABLE savings_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    selected_total DECIMAL(10,2) NOT NULL,
    cheapest_total DECIMAL(10,2) NOT NULL,
    most_expensive_total DECIMAL(10,2) NOT NULL,
    policy_limit_total DECIMAL(10,2),
    savings_vs_expensive DECIMAL(10,2) NOT NULL,
    premium_vs_cheapest DECIMAL(10,2) NOT NULL,
    narrative TEXT NOT NULL,                        -- Claude-generated human-readable summary
    narrative_html TEXT,                            -- formatted version for display
    policy_status VARCHAR(20) NOT NULL,             -- compliant | warning | violation
    policy_checks JSONB NOT NULL,                   -- array of individual check results
    slider_positions JSONB,                         -- {leg_id: slider_value} for audit
    generated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### policy_violations
```sql
CREATE TABLE policy_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_leg_id UUID REFERENCES trip_legs(id),
    policy_id UUID NOT NULL REFERENCES policies(id),
    violation_type VARCHAR(20) NOT NULL,            -- block | warn | flag_for_review
    details JSONB NOT NULL,
    traveler_justification TEXT,
    resolved BOOLEAN DEFAULT false,
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_violations_trip ON policy_violations(trip_id);
```

### approval_history
```sql
CREATE TABLE approval_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    approval_id UUID NOT NULL REFERENCES approvals(id) ON DELETE CASCADE,
    action VARCHAR(30) NOT NULL,                    -- created | viewed | approved | rejected | changes_requested | escalated | commented | reminder_sent
    actor_id UUID NOT NULL REFERENCES users(id),
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approval_history ON approval_history(approval_id);
```

### notifications
```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    type VARCHAR(50) NOT NULL,                      -- approval_requested | approval_decided | changes_requested | escalated | reminder
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    reference_type VARCHAR(50),                     -- trip | approval
    reference_id UUID,
    is_read BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id, is_read);
```

---

## Schema Modifications to Existing Tables

### trips — add fields
```sql
ALTER TABLE trips ADD COLUMN submitted_at TIMESTAMPTZ;
ALTER TABLE trips ADD COLUMN approved_at TIMESTAMPTZ;
ALTER TABLE trips ADD COLUMN rejected_at TIMESTAMPTZ;
ALTER TABLE trips ADD COLUMN rejection_reason TEXT;
```

### policies — expand schema
```sql
CREATE TABLE policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rule_type VARCHAR(50) NOT NULL,
    -- Types: max_price, cabin_restriction, advance_booking,
    --        preferred_airline, max_stops, time_restriction,
    --        hotel_rate_limit, approval_threshold

    conditions JSONB NOT NULL DEFAULT '{}',
    threshold JSONB NOT NULL,
    action VARCHAR(20) DEFAULT 'warn',              -- block | warn | flag_for_review | info
    severity INTEGER DEFAULT 5,                     -- 1-10, used for sorting violations
    exception_roles JSONB DEFAULT '[]',             -- ["admin", "vp"]
    is_active BOOLEAN DEFAULT true,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## API Endpoints

### Policy Management (Admin only)

#### GET /api/policies
List all active policies.
```json
// Response 200
{
    "policies": [
        {
            "id": "uuid",
            "name": "Max Domestic Economy Fare",
            "description": "Economy flights within Canada/US must not exceed $800 CAD",
            "rule_type": "max_price",
            "conditions": {"route_type": "domestic", "cabin": "economy"},
            "threshold": {"amount": 800, "currency": "CAD"},
            "action": "warn",
            "severity": 7,
            "exception_roles": ["admin"],
            "is_active": true
        }
    ]
}
```

#### POST /api/policies
Create a new policy (admin only).
```json
// Request
{
    "name": "Advance Booking Requirement",
    "description": "All flights must be booked at least 7 days in advance",
    "rule_type": "advance_booking",
    "conditions": {},
    "threshold": {"min_days": 7},
    "action": "warn",
    "severity": 5
}
```

#### PUT /api/policies/{policy_id}
Update a policy.

#### DELETE /api/policies/{policy_id}
Soft delete (set `is_active = false`).

### Trip Submission & Savings

#### POST /api/trips/{trip_id}/evaluate
Run policy checks and generate savings report WITHOUT submitting. Used for preview.
```json
// Response 200
{
    "savings_report": {
        "id": "uuid",
        "selected_total": 1240.00,
        "cheapest_total": 1080.00,
        "most_expensive_total": 2310.00,
        "policy_limit_total": 2000.00,
        "savings_vs_expensive": 1070.00,
        "premium_vs_cheapest": 160.00,
        "policy_status": "compliant",
        "narrative": "Shiju selected a Toronto → New York → Chicago itinerary totaling $1,240 CAD...",
        "policy_checks": [
            {
                "policy_id": "uuid",
                "policy_name": "Max Domestic Economy Fare",
                "status": "pass",
                "details": "Leg 1: $320 (limit: $800) | Leg 2: $280 (limit: $800)"
            }
        ],
        "per_leg_summary": [
            {
                "leg_id": "uuid",
                "route": "YYZ → JFK",
                "selected_price": 320.00,
                "cheapest_available": 260.00,
                "savings_actions_taken": "Chose Tuesday departure (saved $310 vs Thursday)",
                "policy_status": "compliant"
            }
        ]
    },
    "violations": [],
    "warnings": [
        {
            "policy_name": "Advance Booking Requirement",
            "message": "Trip is booked 5 days in advance. Policy recommends 7+ days.",
            "action": "warn",
            "requires_justification": false
        }
    ],
    "blocks": []
}
```

#### POST /api/trips/{trip_id}/submit
Submit trip for approval. Runs evaluation, generates savings report, creates approval record.
```json
// Request
{
    "traveler_notes": "Need to arrive by 2pm for client meeting.",
    "violation_justifications": {
        "policy_uuid_here": "Client meeting requires specific timing"
    }
}

// Response 200
{
    "trip_id": "uuid",
    "status": "submitted",
    "approval": {
        "id": "uuid",
        "approver_id": "manager_uuid",
        "approver_name": "Sarah Johnson",
        "status": "pending",
        "created_at": "2026-02-12T15:30:00Z"
    },
    "savings_report": {},
    "notification_sent": true
}

// Response 422 (blocking violations)
{
    "detail": "Trip cannot be submitted due to policy violations",
    "blocks": [
        {
            "policy_name": "Cabin Restriction",
            "message": "Business class not permitted for flights under 6 hours.",
            "policy_id": "uuid"
        }
    ]
}
```

### Approvals

#### GET /api/approvals
Manager's approval queue. Query params: `?status=pending&page=1&limit=20`
```json
// Response 200
{
    "approvals": [
        {
            "id": "uuid",
            "trip": {
                "id": "uuid",
                "title": "Toronto → New York → Chicago",
                "traveler": {
                    "id": "uuid",
                    "name": "Shiju M.",
                    "department": "Finance"
                },
                "total_estimated_cost": 1240.00,
                "legs_count": 4,
                "travel_dates": "Feb 17-25, 2026"
            },
            "savings_report": {
                "policy_status": "compliant",
                "savings_vs_expensive": 1070.00,
                "premium_vs_cheapest": 160.00,
                "narrative": "Shiju selected a Toronto → New York → Chicago itinerary..."
            },
            "warnings_count": 1,
            "violations_count": 0,
            "status": "pending",
            "created_at": "2026-02-12T15:30:00Z"
        }
    ],
    "counts": {
        "pending": 3,
        "approved_today": 5,
        "rejected_today": 1
    }
}
```

#### GET /api/approvals/{approval_id}
Full approval detail with complete savings report, all flight options, and audit history.

#### POST /api/approvals/{approval_id}/decide
Manager action on an approval.
```json
// Approve
{ "action": "approve", "comments": "Looks good, smart savings on the Tuesday departure." }

// Reject
{ "action": "reject", "comments": "Please check if Newark would work — could save another $140." }

// Request changes
{ "action": "changes_requested", "comments": "Can you check Wednesday availability?" }

// Escalate
{ "action": "escalate", "escalate_to": "vp_uuid", "reason": "Over my approval limit" }

// Response 200
{
    "approval_id": "uuid",
    "status": "approved",
    "decided_at": "2026-02-12T16:15:00Z",
    "trip_status": "approved",
    "notification_sent": true
}
```

#### POST /api/approvals/{approval_id}/comment
Add a comment without deciding.
```json
// Request
{ "comment": "Quick question — is the Chicago leg flexible on dates?" }
// Response 200
{ "comment_id": "uuid", "notification_sent": true }
```

### Notifications

#### GET /api/notifications
User's notifications. Query params: `?is_read=false&limit=20`
```json
// Response 200
{
    "notifications": [
        {
            "id": "uuid",
            "type": "approval_decided",
            "title": "Trip Approved",
            "body": "Sarah approved your Toronto → NYC → Chicago trip.",
            "reference_type": "trip",
            "reference_id": "trip_uuid",
            "is_read": false,
            "created_at": "2026-02-12T16:15:00Z"
        }
    ],
    "unread_count": 3
}
```

#### PUT /api/notifications/{notification_id}/read
Mark as read.

#### PUT /api/notifications/read-all
Mark all as read.

### Audit

#### GET /api/audit/trip/{trip_id}
Complete audit trail for a trip (admin and involved parties only).
```json
// Response 200
{
    "trip_id": "uuid",
    "timeline": [
        {
            "timestamp": "2026-02-12T14:00:00Z",
            "event": "trip_created",
            "actor": "Shiju M.",
            "details": { "method": "natural_language", "input": "Toronto to NYC..." }
        },
        {
            "timestamp": "2026-02-12T14:01:00Z",
            "event": "search_executed",
            "actor": "system",
            "details": { "leg": "YYZ → JFK", "options_returned": 47, "cheapest": 260, "most_expensive": 950 }
        },
        {
            "timestamp": "2026-02-12T14:05:00Z",
            "event": "slider_adjusted",
            "actor": "Shiju M.",
            "details": { "leg": "YYZ → JFK", "from": 40, "to": 62 }
        },
        {
            "timestamp": "2026-02-12T14:06:00Z",
            "event": "flight_selected",
            "actor": "Shiju M.",
            "details": { "leg": "YYZ → JFK", "flight": "AC401", "price": 320, "cheapest_available": 260 }
        },
        {
            "timestamp": "2026-02-12T15:30:00Z",
            "event": "trip_submitted",
            "actor": "Shiju M.",
            "details": { "total": 1240, "policy_status": "compliant" }
        },
        {
            "timestamp": "2026-02-12T16:15:00Z",
            "event": "trip_approved",
            "actor": "Sarah Johnson",
            "details": { "comments": "Looks good, smart savings on the Tuesday departure." }
        }
    ]
}
```

---

## Service Layer Details

### 1. Policy Engine (`policy_engine.py`)

Evaluates all active policies against a trip's selected flights.

```python
class PolicyEngine:
    async def evaluate_trip(self, trip, selections, flight_options) -> PolicyEvaluation:
        """Run all active policies. Returns overall status, per-policy results, blocks, warnings."""

    def _get_checker(self, rule_type: str) -> PolicyChecker:
        """Factory for policy checker implementations."""
        # max_price, cabin_restriction, advance_booking,
        # preferred_airline, max_stops, approval_threshold
```

**Individual Checkers:**
- **MaxPriceChecker**: Compares selected price against per-route/cabin limits
- **AdvanceBookingChecker**: Validates minimum days before departure
- **CabinRestrictionChecker**: Restricts cabin class based on flight duration
- **PreferredAirlineChecker**: Flags non-preferred airlines (info level)
- **MaxStopsChecker**: Validates maximum number of stops
- **ApprovalThresholdChecker**: Determines if trip qualifies for auto-approval

### 2. Savings Narrative Generator (`narrative_generator.py`)

Uses Claude API (`claude-sonnet-4-5-20250929`) to produce human-readable savings justification.

- System prompt: professional but human tone, max 4 sentences, include dollar amounts
- Includes per-leg comparisons (selected vs cheapest vs fastest)
- Mentions specific tradeoffs and slider positions
- Fallback template if Claude API fails: "Selected ${total} — ${savings} less than most expensive option. Policy status: {status}."
- `temperature: 0.3`, `max_tokens: 500`

### 3. Approval Workflow Service (`approval_service.py`)

Manages the approval state machine and routing.

**State transitions:**
```
pending → approved | rejected | changes_requested | escalated
changes_requested → pending (traveler resubmits)
escalated → approved | rejected
approved/rejected are terminal
```

**Submit flow:**
1. Validate all legs have selections
2. Run policy evaluation
3. Check for blocking violations
4. Save violation justifications
5. Generate savings narrative
6. Create savings report
7. Determine approver (traveler's manager)
8. Create approval record
9. Send notification to approver
10. Update trip status to 'submitted'

**Approver determination:**
1. Traveler's direct manager (from `users.manager_id`)
2. Fallback: any user with 'manager' role in same department
3. If trip exceeds escalation threshold, route to admin

### 4. Notification Service (`notification_service.py`)

Creates in-app notifications. Extensible to email/Slack in later phases.

- `send_approval_request`: Notify manager of pending approval
- `send_decision`: Notify traveler of approve/reject/changes_requested
- `send_escalation`: Notify new approver of escalated request
- `send_comment`: Notify relevant party of new comment

### 5. Audit Service (`audit_service.py`)

Captures and retrieves full audit trail for trips.

Events: trip_created, search_executed, slider_adjusted, flight_selected, flight_deselected, trip_submitted, policy_evaluated, approval_created, approval_viewed, approval_decided, comment_added, trip_resubmitted

Timeline compiled from: trips, search_logs, selections, policy_violations, approval_history, notifications.

---

## Frontend Components

### New File Structure (Phase B additions)
```
src/
├── components/
│   ├── trip/
│   │   ├── TripSubmission.tsx          # Pre-submit review with savings preview
│   │   ├── SelectionSummary.tsx        # Summary of selected flights per leg
│   │   └── ViolationJustification.tsx  # Form for explaining policy overrides
│   ├── savings/
│   │   ├── SavingsCard.tsx             # Hero approval card
│   │   ├── SavingsNarrative.tsx        # Narrative text display
│   │   ├── CostComparisonBar.tsx       # Visual bar: cheapest ← selected → expensive
│   │   ├── PolicyCheckList.tsx         # Pass/warn/fail indicators
│   │   └── LegSavingsDetail.tsx        # Per-leg savings breakdown
│   ├── approval/
│   │   ├── ApprovalQueue.tsx           # Manager's pending list
│   │   ├── ApprovalCard.tsx            # Compact card in the queue
│   │   ├── ApprovalDetail.tsx          # Full detail view
│   │   ├── ApprovalActions.tsx         # Approve/Reject/Comment buttons
│   │   ├── CommentThread.tsx           # Conversation between traveler & manager
│   │   └── ApprovalBadge.tsx           # Status badge
│   ├── policy/
│   │   ├── PolicyManager.tsx           # Admin CRUD interface
│   │   ├── PolicyForm.tsx              # Create/edit policy form
│   │   ├── PolicyCard.tsx              # Policy display card
│   │   └── PolicyIndicator.tsx         # Inline pass/warn/block icon
│   ├── notifications/
│   │   ├── NotificationBell.tsx        # Header bell with unread count
│   │   ├── NotificationDropdown.tsx    # Dropdown list
│   │   └── NotificationItem.tsx        # Single notification row
│   ├── audit/
│   │   ├── AuditTimeline.tsx           # Vertical timeline
│   │   └── AuditEvent.tsx              # Single event card
├── pages/
│   ├── TripReview.tsx                  # Pre-submission review page
│   ├── ApprovalDashboard.tsx           # Manager's main view
│   ├── ApprovalDetailPage.tsx          # Full approval with savings card
│   ├── PolicyManagement.tsx            # Admin policy config page
│   └── TripAudit.tsx                   # Audit trail view
├── stores/
│   ├── approvalStore.ts
│   ├── notificationStore.ts
│   └── policyStore.ts
```

### Savings Card (`SavingsCard.tsx`)

The centerpiece component for both travelers (pre-submit) and managers (approval).

```
┌──────────────────────────────────────────────────────────┐
│  Toronto → New York → Chicago → Toronto                  │
│  Feb 17-25, 2026 · Shiju M. · Finance                   │
│──────────────────────────────────────────────────────────│
│  $1,240 CAD                                              │
│  ██████████████░░░░░░░░░░ 62% of policy budget           │
│──────────────────────────────────────────────────────────│
│  [Claude-generated narrative in highlighted box]         │
│──────────────────────────────────────────────────────────│
│  Cheapest: $1,080  |  Most Expensive: $2,310             │
│──────────────────────────────────────────────────────────│
│  Policy Checks                                           │
│  ✅ Max domestic fare          $320 < $800               │
│  ⚠️  Advance booking           5 days (min: 7)           │
│  ✅ Cabin restriction          Economy ✓                 │
│──────────────────────────────────────────────────────────│
│  ▸ View per-leg details                                  │
│──────────────────────────────────────────────────────────│
│  Traveler note: "Need to arrive by 2pm..."               │
│──────────────────────────────────────────────────────────│
│  [Approve]    [Comment]    [Decline]                     │
└──────────────────────────────────────────────────────────┘
```

### Approval Queue (`ApprovalQueue.tsx`)

Manager's primary view. Tab filter (Pending/Approved/Rejected/All), sort by newest/cost/warnings. Cards show trip summary, cost, policy status, and time since submission.

### Notification Bell (`NotificationBell.tsx`)

Header icon with unread count badge. Poll every 30 seconds. Click opens dropdown with recent notifications. Click notification navigates to relevant trip/approval.

### Policy Manager (`PolicyManager.tsx`)

Admin-only CRUD. Policy cards with name, description, rule type, action, severity, exceptions. PolicyForm modal with dynamic fields based on rule type.

### Audit Timeline (`AuditTimeline.tsx`)

Vertical timeline with color-coded dots (blue=user, green=approval, amber=warning, gray=system). Expandable details per event.

---

## Updated Navigation (Sidebar)

```
├── New Trip           (all roles)
├── My Trips           (all roles) — status badges
├── Approvals          (manager, admin) — pending count badge
├── Dashboard          (all roles) — placeholder for Phase D
├── Policies           (admin only)
├── ──────────
└── Profile / Settings
```

---

## Seed Data (Phase B additions)

### Policies
1. Max Domestic Economy: $800 CAD, warn, severity 7
2. Max International Economy: $2,500 CAD, warn, severity 8
3. Max Domestic Business: $2,000 CAD, block, severity 9
4. Cabin Restriction: Economy only for flights ≤ 6 hours, warn, severity 6
5. Advance Booking: Minimum 7 days, warn, severity 5
6. Preferred Airlines: Air Canada (AC), WestJet (WS), info, severity 3
7. Max Stops: 2 stops maximum, warn, severity 4
8. Auto-Approve Threshold: Trips under $500 total, info, severity 1

### Demo Trip
Pre-populated completed trip with 4 legs, selections, savings report, and pending approval from Sarah.

---

## Environment Variables (Phase B additions)

```env
NOTIFICATION_POLL_INTERVAL_SECONDS=30
NARRATIVE_MAX_TOKENS=500
NARRATIVE_MODEL=claude-sonnet-4-5-20250929
```

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Claude API fails during narrative | Fall back to template-based narrative. Log failure. |
| No manager found for traveler | Show error: "No approver configured. Please contact admin." |
| Manager tries to approve own trip | 403: "Cannot approve your own trip." |
| Trip resubmitted after changes_requested | Reset approval to pending, notify approver, append to audit |
| Concurrent approval attempts | Optimistic locking on approval.updated_at |

---

## Build Order (Within Phase B)

```
Step 1: Policy Engine
   - Expanded policy model + migration
   - PolicyEngine service with all checkers
   - Policy CRUD endpoints (admin)
   - Frontend: PolicyManager page + PolicyForm

Step 2: Savings Narrative
   - NarrativeGenerator service (Claude API)
   - SavingsReport model + migration
   - /evaluate endpoint (preview without submitting)
   - Frontend: SavingsCard + CostComparisonBar + PolicyCheckList

Step 3: Trip Submission Flow
   - ApprovalService.submit_trip (full flow)
   - ViolationJustification handling
   - /submit endpoint
   - Frontend: TripSubmission page with preview + submit

Step 4: Approval Workflow
   - Approval model + migration
   - Decision endpoint (approve/reject/escalate)
   - Comment endpoint
   - Frontend: ApprovalQueue + ApprovalDetail + ApprovalActions

Step 5: Notifications & Audit
   - Notification model + service
   - NotificationBell + dropdown (polling)
   - AuditService + timeline endpoint
   - AuditTimeline component
   - End-to-end testing of full flow

Step 6: Integration & Polish
   - Update Sidebar with new nav items + badges
   - Trip status badges throughout the app
   - Demo data seeding
   - Edge case handling
   - Loading and error states for all new components
```

---

## Success Criteria for Phase B

Phase B is complete when:

1. Admin can create, edit, enable/disable travel policies
2. When a traveler selects flights, policy engine evaluates all active policies
3. Blocking violations prevent submission; warnings allow with justification
4. System generates a human-readable savings narrative via Claude API
5. Traveler can preview the savings card before submitting
6. Trip submission creates an approval request routed to the traveler's manager
7. Manager sees pending approvals in a clean queue with summary cards
8. Manager can approve, reject, request changes, or escalate — each with comments
9. Both parties receive in-app notifications for status changes and comments
10. Complete audit timeline is available for any trip
11. The savings card is clear enough that a manager can approve in under 10 seconds
12. Narrative fallback works if Claude API is unavailable

---

---

## Price Intelligence Advisor (Post-Phase B)

An LLM-powered price intelligence system that synthesizes multiple pricing signals into actionable book/wait/watch recommendations for corporate travelers.

### Architecture

**Three-layer signal pipeline:**

1. **Amadeus Analytics Service** (`amadeus_analytics_service.py`)
   - Fetches route seasonality from Amadeus air-traffic busiest-period API
   - Computes peak/shoulder/off-peak months with traveler score percentiles
   - Fetches route popularity via most-booked destinations API
   - 24-hour Redis cache for analytics data

2. **Parametric Price Forecast** (`price_forecast_service.py`)
   - Days-to-departure (DTD) curve: U-shaped pricing (sweet spot = 15-42 days out)
   - Day-of-week multiplier: Tuesday cheapest, Friday most expensive
   - Seasonality multiplier from Amadeus analytics
   - Event impact from PredictHQ
   - Seats remaining scarcity signal
   - Historical price trend from search_logs
   - Outputs: predicted price, confidence band, booking window position, urgency score

3. **LLM Price Advisor** (`price_advisor_service.py`)
   - Orchestrates all signals into a structured prompt for Claude Sonnet
   - Claude synthesizes signals into natural-language recommendation
   - Returns: recommendation (book/wait/watch), confidence score, headline, analysis, factors list, timing advice, savings potential
   - Rule-based fallback if Claude API fails
   - 30-minute Redis cache per search_id

### API Endpoints
- `GET /api/search/{leg_id}/advisor` — LLM price advice
- `GET /api/search/{leg_id}/price-trend` — Historical prices from search_logs
- `GET /api/search/{leg_id}/calendar?year=YYYY&month=M` — Month calendar prices

### Frontend
- `PriceAdvisorPanel.tsx` — Displays recommendation badge, confidence bar, headline, analysis, factors with impact indicators, timing advice
- Integrated below the month calendar in search results

### Future Improvements

- **v2: Route-Specific Calibration** — After 30+ days of price tracking data per route, calibrate the DTD curve and seasonality multipliers to match observed patterns for specific city pairs
- **v3: ML Model Training** — Train Prophet/XGBoost model on accumulated search_logs across all routes. Features: DTD, day-of-week, month, route pair, cabin class, seats remaining. Replaces parametric model for routes with sufficient history
- **v4: Fare Bucket Detection** — Detect airline fare bucket transitions from seats_remaining patterns (e.g., seats dropping from 9 to 4 signals a fare class change and imminent price increase)
- **Amadeus Production Tier** — Move from test API to production for broader route coverage and more accurate analytics data
- **Historical Price Comparison** — Once 12+ months of data exists, compare current price to "same week last year" for the route
- **Cross-Route Intelligence** — Identify patterns across similar routes (e.g., all transatlantic routes have similar DTD curves) to bootstrap new routes with limited data

---

---

## Search Experience v2: Airline×Date Matrix + Smart Justification + UI Modernization

A comprehensive upgrade to the flight search and selection experience. Transforms the flat search results into an interactive, data-rich comparison tool with intelligent justification when travelers choose non-optimal flights.

### Problem Statement

The Phase A search experience has several limitations:
1. **Flat flight list** — no cross-airline × date comparison; travelers scroll through cards without seeing the full picture
2. **Flexibility limits visibility** — `flexibility_days` (0-3) restricts both which dates are searched AND displayed; calendar shows the full month but the flight list doesn't
3. **No justification for non-optimal choices** — `Selection.justification_note` exists in the DB but is never populated; managers approve blindly
4. **Redundant UI sections** — same airline/price data appears in the Cheapest-by-Airline grid, Alternatives accordion, and flight list
5. **Visual flatness** — black-on-white with no color hierarchy, oversized flight cards, wall-of-text advisor panel

### Design Principles

- **Flexibility controls booking policy, not display** — users always see ±7 days of pricing regardless of their flexibility setting
- **One source of truth per visual** — no redundant sections showing the same data differently
- **Color communicates value** — green = cheap, amber = mid, red = expensive; throughout
- **Compact by default, expandable on demand** — dense rows, collapsible sections
- **Justification is contextual, not bureaucratic** — preset reasons + free text, proportional to savings amount

---

### 1. Search Backend: Wider Date Window

**File:** `backend/app/services/search_orchestrator.py`

**Current behavior:** Searches ±flexibility_days (0-3) on ALL airport pairs. Filters `is_alternate_date=True` flights out of `all_options`.

**New behavior:**
- Always search **±7 days** on the **primary airport pair** (origin→destination), regardless of flexibility_days
- Use flexibility_days only for **nearby airport pairs** (to limit query volume)
- Include ALL flights in `all_options` — stop filtering out `is_alternate_date`
- Add `within_flexibility: bool` tag to each flight so the UI can distinguish bookable vs. comparison-only dates
- Total queries: 15 (primary) + flex×nearby_pairs, parallel batched

**Cache fix:** Never cache empty results. In `_search_with_cache()`, only call `cache_service.set_flights()` when `len(flights) > 0`.

```python
# search_orchestrator.py changes

# 1. Build date range: always ±7 for primary pair
primary_dates = [preferred_date + timedelta(days=d) for d in range(-7, 8)]
flex_dates = [preferred_date + timedelta(days=d) for d in range(-flex, flex + 1)]

# 2. Primary pair searches all 15 dates
for d in primary_dates:
    search_tasks.append((orig_primary, dest_primary, d, ...))

# 3. Nearby pairs only search flex_dates
for orig in nearby_origins:
    for dest in nearby_dests:
        for d in flex_dates:
            search_tasks.append((orig, dest, d, ...))

# 4. Tag flights
for f in flights:
    dep_date = parse_date(f["departure_time"])
    f["within_flexibility"] = abs((dep_date - preferred_date).days) <= flex

# 5. all_options includes everything (no filtering)
all_options = scored_flights[:100]
```

---

### 2. Airline × Date Price Matrix

**File:** `frontend/src/components/search/AirlineDateMatrix.tsx` (exists, needs enhancement)

A dense, interactive table showing price per airline per date. Built entirely client-side from `all_options`.

**Data transformation:**
- Group `all_options` by `airline_name` → `departure_date` → cheapest FlightOption per cell
- Compute quartiles (Q1, Q3) across all prices for color coding
- Sort airlines by cheapest overall price (excluded airlines pushed to bottom)

**Layout:**
```
┌────────────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
│ Airline        │ Jul 12  │ Jul 13  │ Jul 14  │ Jul 15★ │ Jul 16  │
├────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Icelandair     │ $1,548  │ $1,302  │ $1,445  │ $1,768  │ $1,612  │
│ from $1,302    │ 🟢      │ 🟢 ★    │ 🟢      │ 🟡      │ 🟢      │
├────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Turkish        │ $3,200  │ $3,100  │ —       │ $3,777  │ $3,400  │
│ from $3,100    │ 🔴      │ 🔴      │         │ 🔴      │ 🔴      │
├────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ ░ Azores ░     │ ░$1,400 │ ░$1,200 │ ░—      │ ░$1,548 │ ░$1,350 │
│ ░ excluded ░   │ ░       │ ░       │ ░       │ ░       │ ░       │
└────────────────┴─────────┴─────────┴─────────┴─────────┴─────────┘
```

**Interactions:**
- Click a cell → selects that specific FlightOption (calls `onFlightSelect`)
- Hover a cell → tooltip with stops, duration, departure time
- Click column header → highlights that date, scrolls to it in calendar
- Preferred date column has subtle highlight/border
- Dates outside flexibility window shown with subtle indicator (dashed border or muted header)
- Sticky first column (airline name + cheapest price)
- Horizontal scroll for many dates

**Visual coding:**
- Cell background: green (≤Q1), amber (Q1-Q3), red (≥Q3)
- Bold price = cheapest for that airline (row best)
- ★ = cheapest airline + date combination (global best)
- Excluded airlines: grayed out with strikethrough, not clickable
- Preferred date column: subtle blue left border

---

### 3. Compact Flight List (replaces current cards)

**File:** `frontend/src/components/search/FlightOptionCard.tsx` (rewrite)

Replace tall cards with dense table-style rows similar to Google Flights / Skyscanner.

```
┌─────────────────────────────────────────────────────────────────────┐
│ ✈ Icelandair FI614    11:10p→2:40p+1   10h30m  1stop  $1,768  [→] │
│   YYZ → KEF → LGW    Business          Jul 15   Score: 87.2       │
├─────────────────────────────────────────────────────────────────────┤
│ ✈ Turkish TK18        6:25p→12:40p+1   12h15m  1stop  $3,777  [→] │
│   YYZ → IST → LHR    Business          Jul 15   Score: 76.1       │
├─────────────────────────────────────────────────────────────────────┤
│ 🏆 Recommended                                                      │
│ ✈ Azores S4120        8:45p→3:35p+1   13h50m  2stop  $1,548  [→] │
│   YYZ → PDL → LIS → LHR  Business     Jul 15   Score: 81.3       │
└─────────────────────────────────────────────────────────────────────┘
```

**Each row:** airline icon/code, flight number, departure→arrival times, duration, stops, price (colored badge), select button.
**Second line:** route (with stop airports), cabin, date, score.
**Badges:** "Recommended", "Cheapest", "Fastest", "Nonstop", "Alt Airport", "Flex Date", "Outside flexibility" — as small colored pills.
**Height target:** ~48px per row (vs ~80px current cards).

---

### 4. Compact Price Advisor

**File:** `frontend/src/components/search/PriceAdvisorPanel.tsx` (rewrite)

Replace wall-of-text with collapsible banner.

**Collapsed (default):**
```
┌──────────────────────────────────────────────────────────────────┐
│ 🟢 Book Now — LOW price confirmed by Google Flights. Events     │
│    may push prices up.                              [Details ▸] │
└──────────────────────────────────────────────────────────────────┘
```

**Expanded (click Details):**
Shows the full analysis with bullet points (not paragraph text), factors with colored impact indicators, and timing advice.

---

### 5. Remove Redundant Sections

**File:** `frontend/src/components/search/SearchResults.tsx`

**Remove:**
- "Alternatives" accordion (Cheaper Dates, Nearby Airports, Connecting) — this data is now visible in the matrix and tagged on flight rows
- "Cheapest by Airline" chip grid — replaced by matrix
- Separate "Recommended" card — integrated as highlighted row in flight list

**Replace with:**
- Matrix (section 2 above)
- Compact flight list with badges (section 3 above)
- Airline filter chips (compact pills, kept for quick filtering)

**New section order:**
1. Search metadata bar (compact)
2. Event warning banner (if applicable)
3. Month calendar (existing, unchanged)
4. Price advisor (compact banner)
5. Airline × Date matrix
6. Airline filter chips
7. Flight list (compact rows with badges)

---

### 6. Smart Justification Flow

#### 6a. Analyze-Selection Endpoint

**File:** `backend/app/routers/search.py` — `POST /{trip_leg_id}/analyze-selection` (exists)

Compares selected flight against all alternatives (filtered by user's excluded airlines):
- `cheapest_same_date`: cheapest flight on same date, different airline
- `cheapest_any_date`: overall cheapest flight across all searched dates
- `cheapest_same_airline`: same airline, cheaper date
- `savings_amount` and `savings_percent`
- `justification_required`: true if savings ≥ $100 or ≥ 10%
- `justification_prompt`: LLM-generated prompt (only when required)

#### 6b. Justification Service

**File:** `backend/app/services/justification_service.py` (exists)

LLM-powered prompt generation using `claude-sonnet-4-5-20250929`:
- System prompt: helpful corporate travel advisor, not judgmental
- Generates 2-3 sentence contextual prompt acknowledging the selection and stating alternatives
- `max_tokens=200`, `temperature=0.3`
- Rule-based fallback if LLM fails

#### 6c. Justification Modal

**File:** `frontend/src/components/search/JustificationModal.tsx` (exists, needs enhancement)

**Tiered justification based on savings amount:**
- **< $100 savings**: No modal, confirm directly
- **$100-$500 savings**: Inline banner in selection bar with quick-justify presets
- **> $500 savings**: Full modal with LLM prompt + alternatives + textarea

**Quick-justify presets** (clickable chips, select one or more):
- "Schedule alignment with meetings"
- "Loyalty program / status"
- "Nonstop preference"
- "Client / customer requirement"
- "Personal safety / comfort"
- Custom: free-text input

**Full modal content:**
1. Header with savings badge
2. LLM-generated prompt (styled callout box)
3. Side-by-side comparison table: Selected vs Cheapest (highlighting what you gain: nonstop, shorter, better times)
4. Alternative flight cards with "Switch" buttons
5. Quick-justify preset chips
6. Optional free-text elaboration (required for >$500)
7. "Confirm Selection" + "Cancel"

---

### 7. Enhanced Selection Bar

**File:** `frontend/src/pages/TripSearch.tsx`

The bottom selection bar should show savings context:

```
┌──────────────────────────────────────────────────────────────────┐
│ Selected: Turkish TK18 · $3,777              $2,009 more than   │
│ YYZ → IST → LHR · Jul 15 · 1 stop          cheapest (Icelandair│
│                                              $1,768)             │
│                              [Clear]  [Confirm Selection]        │
└──────────────────────────────────────────────────────────────────┘
```

- Shows savings differential in amber/red based on amount
- "Analyzing..." state while calling analyze-selection
- Smooth transition to justification mode

---

### 8. User Travel Preferences

#### 8a. Backend

**File:** `backend/app/models/user.py` — `travel_preferences: JSONB` column (exists)

Stores: `{"excluded_airlines": ["Azores Airlines"], "preferred_cabin": "business"}`

**File:** `backend/app/routers/users.py` — `GET/PATCH /users/me/preferences` (exists)

**Migration:** `phase_e_001_user_travel_preferences.py` (exists, applied)

#### 8b. Frontend Preferences UI

**File:** `frontend/src/pages/Settings.tsx` or inline in search

Airline preference toggles:
- List airlines seen in recent searches
- Toggle switch to exclude/include each
- Excluded airlines are grayed in matrix and excluded from justification threshold

---

### 9. Color and Visual Depth

Applied across all search components:

- **Price badges**: Green pill ($1,548), amber pill ($3,777), red pill ($10,344) — based on quartile position
- **Card shadows**: `shadow-sm` on hover, `shadow-md` on selected
- **Section backgrounds**: Alternating subtle gray (`bg-muted/20`) for visual separation
- **Airline brand accents**: Subtle colored left border on flight rows (optional, derived from airline code)
- **Gradient headers**: Section headers with subtle gradient underline
- **Selection highlight**: Selected flight row gets `ring-2 ring-primary` treatment
- **Outside-flexibility indicator**: Dashed border or muted opacity for dates beyond ±flexibility_days

---

### 10. Performance & Loading

- **Matrix skeleton**: Show grid skeleton with shimmer while search runs (not blank space)
- **Lazy-load below fold**: Advisor panel, event panel, hotel search load when scrolled to
- **Optimistic matrix**: Show matrix immediately with calendar data (cheapest-per-date only), then fill in airline breakdown as full search completes
- **Don't cache empty results**: `_search_with_cache()` only caches when `len(flights) > 0`

---

### 11. Calendar ↔ Matrix Linking

- Clicking a date in the calendar highlights that column in the matrix
- Clicking a matrix cell updates the calendar selection ring
- Both components use the same `selectedDate` state (lifted to SearchResults)

---

### 12. Intelligence Features (Future)

- **Price trend indicators**: Tiny ↑/↓ arrows in matrix cells showing if price is rising or falling vs. last search
- **"You always pick nonstop" learning**: Track user selection patterns and pre-sort/highlight based on history
- **Team travel awareness**: Surface "2 colleagues are also flying to London that week" from trip overlap detection
- **Price watch per cell**: "Set alert" button on matrix cells for specific airline+date combos

---

### Implementation Order

```
Step 1: Backend search fix (P0)
   - Widen search to ±7 days on primary pair
   - Include all flights in all_options
   - Add within_flexibility tag
   - Fix empty result caching

Step 2: Compact UI overhaul (P1)
   - Compact flight rows (FlightOptionCard rewrite)
   - Compact advisor (collapsible banner)
   - Remove redundant sections
   - New SearchResults layout order

Step 3: Matrix enhancement (P1)
   - Matrix now has full date data
   - Hover tooltips on cells
   - Calendar ↔ matrix date linking
   - Preferred date column highlight

Step 4: Justification UX (P2)
   - Quick-justify presets
   - Tiered justification (inline vs modal based on savings)
   - Side-by-side comparison in modal
   - Enhanced selection bar with savings context

Step 5: Visual polish (P1)
   - Color-coded price badges throughout
   - Skeleton loading states
   - Card shadows and depth
   - Section backgrounds

Step 6: Performance (P3)
   - Lazy-load sections
   - Optimistic matrix rendering
   - Background pre-fetch of adjacent dates
```

---

### Files Summary

| File | Change |
|------|--------|
| `backend/app/services/search_orchestrator.py` | Widen search, include all flights, fix caching |
| `backend/app/services/justification_service.py` | Exists — no changes |
| `backend/app/routers/search.py` | analyze-selection endpoint exists — no changes |
| `backend/app/models/user.py` | travel_preferences exists — no changes |
| `backend/app/routers/users.py` | preferences endpoints exist — no changes |
| `frontend/src/components/search/AirlineDateMatrix.tsx` | Enhance with tooltips, date linking, preferred column |
| `frontend/src/components/search/FlightOptionCard.tsx` | **Rewrite** — compact rows |
| `frontend/src/components/search/SearchResults.tsx` | **Major rewrite** — new layout, remove redundancy |
| `frontend/src/components/search/JustificationModal.tsx` | Enhance with presets, tiered UX, comparison |
| `frontend/src/components/search/PriceAdvisorPanel.tsx` | **Rewrite** — collapsible banner |
| `frontend/src/pages/TripSearch.tsx` | Enhanced selection bar with savings context |

---

### Success Criteria

1. **Matrix works**: 15 date columns filled with multi-airline data, color-coded, clickable
2. **Compact layout**: Search results page is ~50% shorter in vertical space
3. **No redundancy**: Each piece of data appears exactly once
4. **Justification flows**: Selecting expensive flight triggers contextual prompt with presets
5. **Visual richness**: Green/amber/red throughout, shadows, depth, not flat
6. **Performance**: Matrix shows skeleton while loading, fills progressively
7. **Calendar ↔ matrix sync**: Clicking either highlights the corresponding date

---

## Phase Overview

| Phase | Scope | Estimated Effort |
|-------|-------|-----------------|
| **A** | Foundation + Search + UI | ~40% |
| **B** | Policy + Justification + Approvals + Search v2 | ~25% |
| **C** | Events + Hotels + Alerts | ~20% |
| **D** | Analytics + Collaboration + Polish | ~15% |
