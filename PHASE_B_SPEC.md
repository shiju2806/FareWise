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

## Phase Overview

| Phase | Scope | Estimated Effort |
|-------|-------|-----------------|
| **A** | Foundation + Search + UI | ~40% |
| **B** | Policy + Justification + Approvals | ~25% |
| **C** | Events + Hotels + Alerts | ~20% |
| **D** | Analytics + Collaboration + Polish | ~15% |
