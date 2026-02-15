# Unified Trips Experience — My Trips + New Trip + Airline Matrix + Chat

**Created:** 2026-02-15
**Status:** Ready for implementation
**Depends on:** Existing search experience (SEARCH_UX_V3), backend trip/approval/policy APIs

---

## Executive Summary

Replace the separate "My Trips" and "New Trip" pages with a **single unified Trips page** where the calendar IS the home base. Existing trips appear as colored bars on the calendar. Empty dates are selectable for new searches. Clicking a trip bar reveals the airline-date price matrix for that leg below the calendar. The same matrix appears when selecting empty dates for new bookings. A per-trip chat thread replaces fragmented communication (justification notes, approval comments, Slack/email side-channels).

**One surface. No duplication. No context switching.**

---

## Design Philosophy & Competitive Inspiration

### Core Principles

**1. Calendar-as-home (inspired by Google Calendar + TripIt Pro)**
Google Calendar taught users that a month grid with colored event bars is the fastest way to understand "what's happening when." TripIt Pro applied this to travel — upcoming trips are prominent, past trips fade. We merge both: the calendar shows trips AND prices AND is the entry point for new bookings.

**2. Price-in-context (inspired by Google Flights Date Grid)**
Google Flights' date grid — departure dates across the top, return dates down the side, prices in cells with green-to-red shading — is the gold standard for flexible date pricing. We apply the same pattern but integrate it INTO the trips view rather than hiding it behind a separate search page. When you click a trip bar, the airline-date matrix appears below the calendar showing prices around your booked date, so you immediately see "did I get a good deal?"

**3. Action-first hierarchy (inspired by Navan)**
Navan leads with what needs attention — pending approvals, unbooked hotels, expiring fares. We adopt the same pattern: an action bar at the top collapses when nothing is pending. Users never wonder "do I need to do anything?"

**4. Progressive disclosure (inspired by Linear + Skyscanner)**
Linear's board/list/timeline toggle shows the same data three ways. Skyscanner's Best/Cheapest/Fastest tabs let users re-sort instantly. We don't overwhelm — the calendar shows overview, clicking reveals detail, sliding reveals alternatives.

**5. Contextual communication (inspired by GitHub Issues)**
GitHub's per-issue comment thread keeps all discussion in context. We apply this to trips: every message, status change, and approval decision lives in one per-trip chat thread. No more "check your email for Sarah's comment about the Newark alternative."

**6. Unified booking flow (inspired by TravelPerk)**
TravelPerk achieves 95%+ policy compliance by reducing friction. Our calendar-as-booking-surface means travelers never leave their "home" view to start a search. Select dates → type destination → see prices → book. Three steps, one page.

---

## Architecture: What Changes

### Pages

| Before | After |
|--------|-------|
| `MyTrips.tsx` — flat list of trip cards | **REMOVED** |
| `NewTrip.tsx` or `TripSearch.tsx` — separate search page | **KEPT** but also accessible from unified view |
| (none) | `Trips.tsx` — **NEW** unified trips page (becomes sidebar default) |

### New Components

```
frontend/src/
├── pages/
│   └── Trips.tsx                          # NEW — the unified trips home
├── components/
│   └── trips/
│       ├── TripCalendar.tsx               # NEW — month grid with trip bars + date selection
│       ├── TripBar.tsx                    # NEW — colored bar spanning trip dates
│       ├── DateRangeSelector.tsx          # NEW — click/drag empty dates to start search
│       ├── AirlinePricePanel.tsx          # NEW — context-aware matrix below calendar
│       ├── TripSlideOver.tsx              # NEW — right panel with trip detail tabs
│       ├── TripDetailTabs.tsx             # NEW — Details | Flights | Hotel | Chat
│       ├── TripChat.tsx                   # NEW — per-trip conversation thread
│       ├── ChatMessage.tsx                # NEW — single message (bubble style)
│       ├── ChatSystemEvent.tsx            # NEW — system event (status change, auto-approve)
│       ├── ActionBar.tsx                  # NEW — top alerts strip
│       ├── QuickDestinationInput.tsx      # NEW — "Where to?" input for new bookings
│       ├── TripStatusBadge.tsx            # NEW — reusable status badge
│       └── CalendarNav.tsx               # NEW — month navigation + today button
```

### Reused Components (from existing search experience)

| Component | Used Where | Adaptation |
|-----------|-----------|------------|
| `AirlineDateMatrix.tsx` | Inside `AirlinePricePanel.tsx` | Same matrix, different data source (historical for existing trips, live for new searches) |
| `FlightOptionCard.tsx` | Inside `TripSlideOver.tsx` flight tab | Compact flight rows in trip detail |
| `PriceAdvisorPanel.tsx` | Inside `AirlinePricePanel.tsx` header | Price gauge bar contextual to the selected leg |
| `WhatIfSlider.tsx` | Inside slide-over for new searches | Cost↔convenience slider during booking |
| `MonthCalendar.tsx` | **Pattern reference only** | TripCalendar uses same quartile color logic but different layout |

### Backend Changes

**New endpoints:**

```
GET  /api/trips/calendar?month=2026-02          # trips + dates for calendar rendering
GET  /api/trips/{trip_id}/chat                   # get chat messages
POST /api/trips/{trip_id}/chat                   # send message
GET  /api/trips/{trip_id}/price-context/{leg_id} # airline-date matrix data for a booked leg
POST /api/trips/quick-search                     # lightweight search from calendar date selection
```

**New database table:**

```sql
CREATE TABLE trip_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES users(id),
    message_type VARCHAR(20) NOT NULL DEFAULT 'user',   -- user | system | status_change
    content TEXT NOT NULL,
    metadata JSONB,                                      -- for system events: {old_status, new_status, etc.}
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trip_messages ON trip_messages(trip_id, created_at);
```

**Migration:** Existing `approval.comments`, `traveler_notes`, and `violation_justifications` should auto-seed as initial chat messages when a trip is submitted, so the conversation thread has full history.

---

## Component Specifications

### 1. Trips.tsx — The Unified Page

The main page layout. This replaces both "My Trips" and serves as the entry point for new trips.

**Layout structure:**
```
┌──────────────────────────────────────────────────────────────────────┐
│  ActionBar (alerts strip — collapses when empty)                     │
├──────────────────────────────────────────────────────────────────────┤
│  CalendarNav (month name, ◄ ► arrows, Today button, view options)   │
├──────────────────────────────────────────────────────────────────────┤
│  TripCalendar (month grid with trip bars)                            │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Mon    Tue    Wed    Thu    Fri    Sat    Sun               │   │
│  │  ...                                                         │   │
│  │  16    ┌─17 ──── 18 ──── 19 ──── 20─┐    21     22         │   │
│  │        │ YYZ→JFK  ✅  $887           │                      │   │
│  │  23    ┌─24 ──── 25─┐                                       │   │
│  │        │ ORD→YYZ ⏳  │   26    27    28                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────┤
│  AirlinePricePanel (appears when trip bar or date range selected)    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  YYZ → JFK · Feb 17                                         │   │
│  │           Feb 14  Feb 15  Feb 16  Feb 17★ Feb 18  Feb 19    │   │
│  │  Air Can   $380    $320    $410   [$320]   $290    $260     │   │
│  │  United    $420    $350    $390    $380    $310    $280     │   │
│  │  Delta     $450    $380    $430    $410    $340    $300     │   │
│  │                                                              │   │
│  │  ✅ Booked: AC401 · $320 · Direct · 1h35m                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘

  ┌─ TripSlideOver (appears from right when trip is clicked) ─────────┐
  │  [Details]  [Flights]  [Hotel]  [💬 Chat (3)]                     │
  │                                                                    │
  │  ...content based on active tab...                                 │
  └────────────────────────────────────────────────────────────────────┘
```

**State management (Zustand store):**
```typescript
interface TripsPageStore {
  // Calendar state
  currentMonth: Date;
  trips: CalendarTrip[];

  // Selection state
  selectedTripId: string | null;
  selectedLegId: string | null;

  // Date selection for new bookings
  dateSelectionMode: boolean;
  selectedDateRange: { start: Date; end: Date } | null;

  // Slide-over
  slideOverOpen: boolean;
  slideOverTab: 'details' | 'flights' | 'hotel' | 'chat';

  // Price panel
  pricePanelData: AirlineDateMatrix | null;
  pricePanelMode: 'historical' | 'live_search';

  // Actions
  setMonth: (month: Date) => void;
  selectTrip: (tripId: string, legId?: string) => void;
  startDateSelection: () => void;
  setDateRange: (range: { start: Date; end: Date }) => void;
  clearSelection: () => void;
}
```

**File:** `frontend/src/pages/Trips.tsx`

---

### 2. ActionBar.tsx — Alerts Strip

A compact strip at the top showing items that need attention. Collapses to zero height when nothing is pending.

**Data source:** `GET /api/trips/calendar?month=YYYY-MM` returns an `alerts` array.

**Alert types and their visual treatment:**

```
┌──────────────────────────────────────────────────────────────────────┐
│  ⏳ 1 pending approval · NYC trip awaiting Sarah     [View →]        │
│  🏨 1 trip needs hotel · Chicago, departs in 5 days  [Book Hotel →]  │
│  📉 Price drop · YYZ→SFO fell to $380 (-18%)        [See Deal →]    │
└──────────────────────────────────────────────────────────────────────┘
```

**Design:**
- Full-width horizontal strip, compact height (~44px per alert, max 3 visible)
- Left color accent per alert type: amber (pending), blue (action needed), emerald (opportunity)
- Each alert is clickable — navigates to the relevant trip/action
- Smooth collapse animation (200ms ease-out) when alerts are resolved
- If more than 3 alerts, show "+2 more" with expand

**Implementation:**
```tsx
// ActionBar.tsx
interface Alert {
  id: string;
  type: 'pending_approval' | 'needs_hotel' | 'price_drop' | 'event_warning' | 'expiring_fare';
  title: string;
  subtitle: string;
  action_label: string;
  action_url?: string;
  trip_id?: string;
  urgency: 'high' | 'medium' | 'low';
}
```

**File:** `frontend/src/components/trips/ActionBar.tsx`

---

### 3. TripCalendar.tsx — The Month Grid

The centerpiece. A month calendar grid where trip days are visually marked with colored bars.

**Grid structure:**
- 7 columns (Mon–Sun), rows for each week of the month
- Each cell: date number (top-left), trip bars overlaid
- Trip bars span across cells for multi-day trips
- Empty cells are interactive — clickable to start date selection

**Trip bar design (TripBar.tsx):**

Each trip gets a bar that spans its date range horizontally across calendar cells:

```
┌─ Feb 17 ──── Feb 18 ──── Feb 19 ──── Feb 20 ─┐
│  YYZ → JFK                    ✅  $887         │
└────────────────────────────────────────────────┘
```

- **Color palette** (muted, accessible, up to 8 trips visible per month):
  - Trip 1: `bg-blue-100 border-blue-400 text-blue-800` (dark mode: `bg-blue-900/40 border-blue-500 text-blue-200`)
  - Trip 2: `bg-teal-100 border-teal-400 text-teal-800`
  - Trip 3: `bg-violet-100 border-violet-400 text-violet-800`
  - Trip 4: `bg-amber-100 border-amber-400 text-amber-800`
  - Trip 5+: cycle from palette

- **Status encoding on the bar:**
  - Draft: dashed border (`border-dashed`), muted opacity (0.7)
  - Submitted/Pending: solid border, small clock icon
  - Approved: solid border, checkmark icon
  - Rejected: solid border with `border-red-400`, X icon
  - Changes Requested: solid border with `border-amber-400`, edit icon

- **Bar content (left to right):**
  - Route label: "YYZ → JFK" (truncated if needed)
  - Status icon (right-aligned)
  - Total cost (right-aligned, smaller text)

- **Multi-leg trips:** ONE bar spanning the full date range with internal leg markers — small vertical divider lines at leg boundaries. Hovering a section of the bar highlights that specific leg. This prevents duplication.

- **Bar interaction:**
  - Click → opens `TripSlideOver` from the right AND loads `AirlinePricePanel` below calendar
  - Hover → tooltip with: trip title, dates, total cost, status, legs count
  - If multiple trips overlap on same dates, bars stack vertically (max 3 visible, "+1 more" indicator)

**Date selection for new bookings:**

When the user clicks an empty date cell:
1. Cell gets a blue selection ring
2. User can click a second date to create a range (or drag)
3. Selected range gets a dashed blue overlay bar
4. `QuickDestinationInput` appears below the calendar (slides down, 200ms)
5. User types destination → triggers search → `AirlinePricePanel` loads with live prices

**Calendar navigation (CalendarNav.tsx):**

```
┌──────────────────────────────────────────────────────────────────────┐
│  ◄   February 2026   ►          [Today]         🗓️ Calendar  📋 List │
└──────────────────────────────────────────────────────────────────────┘
```

- Month navigation arrows
- "Today" pill jumps back to current month
- Calendar/List toggle switches between calendar view and a compact list
- Current day cell has a subtle accent ring (`ring-2 ring-primary/30`)

**Mobile considerations:**
- On mobile (<768px), calendar cells are narrower — trip bars show only the route code (no price)
- Tap a cell to see full details — opens slide-over as a bottom sheet on mobile
- Horizontal scroll if needed for wider trip bars
- Swipe left/right to change months

**File:** `frontend/src/components/trips/TripCalendar.tsx`
**File:** `frontend/src/components/trips/TripBar.tsx`
**File:** `frontend/src/components/trips/DateRangeSelector.tsx`
**File:** `frontend/src/components/trips/CalendarNav.tsx`

---

### 4. AirlinePricePanel.tsx — Context-Aware Price Matrix

This is the **bridge between My Trips and Search**. It appears below the calendar whenever:
- A trip bar is clicked (shows historical prices around the booking date)
- A date range is selected for new booking (shows live search prices)

**Two modes:**

#### Mode 1: Historical Context (clicking existing trip)

Shows the airline-date matrix for the selected leg, centered on the booked date. Data comes from `GET /api/trips/{trip_id}/price-context/{leg_id}`.

```
┌──────────────────────────────────────────────────────────────────────┐
│  YYZ → JFK · Feb 17  ·  Booked: AC401 $320                         │
│                                                                      │
│  ┌─ Price Context (±3 days) ─────────────────────────────────────┐  │
│  │            Feb 14   Feb 15   Feb 16   Feb 17★  Feb 18   Feb 19│  │
│  │  Air Can    $380     $320     $410    [$320]    $290     $260 │  │
│  │  United     $420     $350     $390     $380     $310     $280 │  │
│  │  Delta      $450     $380     $430     $410     $340     $300 │  │
│  │  Porter     $340     $290     $350     $310     $270     $240 │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─ Booking Summary ─────────────────────────────────────────────┐  │
│  │  ✅ AC401 · $320 · Direct · 1h35m · Economy                   │  │
│  │  Cheapest that day: Porter $310 (1 stop, +2h)                 │  │
│  │  Cheapest in window: Porter Feb 19 $240 (2 days later)        │  │
│  │  Saved $130 vs most expensive date · 85% of policy budget     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

#### Mode 2: Live Search (selecting empty dates)

Same matrix layout but with live prices. Data comes from `POST /api/trips/quick-search`.

**File:** `frontend/src/components/trips/AirlinePricePanel.tsx`

---

### 5. TripSlideOver.tsx — Trip Detail Panel

Opens from the right when a trip bar is clicked. Contains tabbed content.

**Slide-over design:**
- Width: 420px on desktop, full-width bottom sheet on mobile
- Slides in from right (300ms ease-out)
- Semi-transparent backdrop on mobile, no backdrop on desktop (calendar remains visible)
- Close button (X) top-right + click outside to close on desktop
- Sticky header with trip title and status badge

**Tabs:** Details | Flights | Hotel | Chat

**File:** `frontend/src/components/trips/TripSlideOver.tsx`
**File:** `frontend/src/components/trips/TripDetailTabs.tsx`

---

### 6. TripChat.tsx — Per-Trip Conversation Thread

Replaces fragmented communication. All discussion about a trip lives here.

**Message types and styling:**

1. **User messages:** Left-aligned for others, right-aligned for self. Sender name + role badge + timestamp.
2. **System events:** Full-width, centered, subtle styling. Used for: trip submitted, approved/rejected, status changes, auto-approve events, price alerts.
3. **Approval decision with comment:** System event format with manager's comment quoted inside.

**What auto-posts as system events:**
- Trip created (with method: natural language / structured form)
- Trip submitted (with approver name)
- Approval decision (approved/rejected/changes_requested + comment)
- Auto-approve (with policy check summary)
- Flight/hotel selection changed
- Price watch alert triggered

**File:** `frontend/src/components/trips/TripChat.tsx`
**File:** `frontend/src/components/trips/ChatMessage.tsx`
**File:** `frontend/src/components/trips/ChatSystemEvent.tsx`

---

### 7. QuickDestinationInput.tsx — Search Entry from Calendar

Appears below the calendar when a date range is selected on empty dates.

**Features:**
- Pre-filled date range from calendar selection
- Two input modes: simple destination input OR natural language description
- Recent/frequent routes shown as clickable chips
- "Search" triggers quick-search and loads AirlinePricePanel
- "Open Full Search" navigates to TripSearch.tsx with context carried over

**File:** `frontend/src/components/trips/QuickDestinationInput.tsx`

---

## Backend Specifications

### GET /api/trips/calendar

Returns all data needed to render the unified trips page for a given month.

**Request:** `GET /api/trips/calendar?month=2026-02`

**Response:**
```json
{
  "month": "2026-02",
  "trips": [
    {
      "id": "trip_uuid",
      "title": "Toronto → New York → Chicago",
      "status": "approved",
      "total_cost": 1454.00,
      "legs": [
        {
          "id": "leg_uuid",
          "sequence": 1,
          "origin": "YYZ",
          "destination": "JFK",
          "date": "2026-02-17",
          "end_date": "2026-02-20",
          "flight_summary": "AC401 · $320 · Direct",
          "hotel_summary": "Courtyard Midtown · $567"
        }
      ],
      "start_date": "2026-02-17",
      "end_date": "2026-02-25",
      "policy_status": "compliant",
      "unread_messages": 2
    }
  ],
  "alerts": [
    {
      "id": "alert_1",
      "type": "pending_approval",
      "title": "1 pending approval",
      "subtitle": "NYC trip · awaiting Sarah",
      "action_label": "View",
      "trip_id": "trip_uuid_2",
      "urgency": "medium"
    }
  ],
  "recent_routes": [
    { "origin": "YYZ", "destination": "JFK", "price_range": [290, 380], "trip_count": 4 }
  ]
}
```

### GET /api/trips/{trip_id}/price-context/{leg_id}

Returns airline-date matrix data for a specific booked leg, showing prices ±3 days around the booked date. Pulls from stored `search_logs` data.

### POST /api/trips/quick-search

Lightweight search for calendar date-selection flow. Returns same matrix format with live prices.

### GET/POST /api/trips/{trip_id}/chat

Chat message CRUD. GET returns messages, POST sends a new message.

---

## Sidebar Navigation Update

```
Sidebar (updated):
├── Trips              ← NEW: replaces both "New Trip" and "My Trips"
├── Approvals           (manager, admin)
├── Price Watches
├── Alerts
├── ──────────
├── Analytics           (manager, admin)
├── My Stats
├── ──────────
├── Policies            (admin)
└── Settings
```

---

## Implementation Priority

```
Phase 1: Calendar Foundation (TripCalendar + TripBar + CalendarNav)
   - Backend: GET /api/trips/calendar endpoint
   - Month grid rendering with proper day alignment
   - Trip data fetching and bar rendering
   - Multi-day bar spanning across cells
   - Status badges and color coding
   - Month navigation + Today button
   - Calendar/List toggle (reuse TripHistory as list view)
   - Mobile responsive layout
   - Update sidebar navigation

Phase 2: TripSlideOver + AirlinePricePanel (Historical)
   - Backend: GET /api/trips/{trip_id}/price-context/{leg_id}
   - Slide-over shell with tabs (Details + Flights)
   - Details tab: cost summary, savings, policy, timeline
   - Flights tab: leg cards using FlightOptionCard
   - AirlinePricePanel historical mode with booking context
   - Connection: click trip bar → load panel + slide-over

Phase 3: TripChat
   - Backend: trip_messages table + migration
   - Backend: GET/POST /api/trips/{trip_id}/chat
   - Backend: auto-post system events on status changes
   - Frontend: TripChat + ChatMessage + ChatSystemEvent
   - Unread count badge on Chat tab

Phase 4: Date Selection + Quick Search (Live Mode)
   - DateRangeSelector: click/drag date selection
   - QuickDestinationInput: destination + NLP input
   - Backend: POST /api/trips/quick-search
   - AirlinePricePanel live mode with sort tabs + price gauge
   - "Open Full Search" navigation

Phase 5: ActionBar + Polish
   - ActionBar with alert types and collapse behavior
   - Skeleton loading states for all components
   - Error states
   - Dark mode support
   - Keyboard navigation
   - End-to-end testing
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/pages/Trips.tsx` | **NEW** | Unified trips page |
| `frontend/src/components/trips/TripCalendar.tsx` | **NEW** | Month grid with trip bars |
| `frontend/src/components/trips/TripBar.tsx` | **NEW** | Colored bar for a trip on calendar |
| `frontend/src/components/trips/CalendarNav.tsx` | **NEW** | Month navigation + view toggle |
| `frontend/src/components/trips/DateRangeSelector.tsx` | **NEW** | Click/drag date selection |
| `frontend/src/components/trips/AirlinePricePanel.tsx` | **NEW** | Context-aware airline-date matrix |
| `frontend/src/components/trips/TripSlideOver.tsx` | **NEW** | Right panel with trip details |
| `frontend/src/components/trips/TripDetailTabs.tsx` | **NEW** | Tabs: Details, Flights, Hotel, Chat |
| `frontend/src/components/trips/TripChat.tsx` | **NEW** | Per-trip conversation thread |
| `frontend/src/components/trips/ChatMessage.tsx` | **NEW** | User message bubble |
| `frontend/src/components/trips/ChatSystemEvent.tsx` | **NEW** | System event row |
| `frontend/src/components/trips/ActionBar.tsx` | **NEW** | Top alerts strip |
| `frontend/src/components/trips/QuickDestinationInput.tsx` | **NEW** | "Where to?" search input |
| `frontend/src/components/trips/TripStatusBadge.tsx` | **NEW** | Reusable status badge |
| `frontend/src/stores/tripsPageStore.ts` | **NEW** | Zustand store for page state |
| `backend/app/routers/trips_calendar.py` | **NEW** | Calendar + price context endpoints |
| `backend/app/routers/trip_chat.py` | **NEW** | Chat message CRUD |
| `backend/app/models/trip_message.py` | **NEW** | TripMessage model |
| `backend/app/services/trip_chat_service.py` | **NEW** | Chat business logic + auto-events |
| `backend/app/services/price_context_service.py` | **NEW** | Historical price matrix builder |
| `frontend/src/components/layout/Sidebar.tsx` | **MODIFY** | Update nav items |
| `backend/app/services/approval_service.py` | **MODIFY** | Post decisions as chat messages |
| `backend/app/services/search_orchestrator.py` | **MODIFY** | Store full matrix in search_logs |

**Total: 20 new files, 3 modified files**

---

## Success Criteria

1. Unified Trips page is the default landing page
2. Calendar shows all trips as colored bars spanning their date ranges
3. Multi-leg trips appear as ONE bar with internal leg markers
4. Clicking a trip bar shows the airline-date price matrix below the calendar
5. Clicking a flight leg in the slide-over updates the matrix to that leg's context
6. Selecting empty dates + typing a destination shows live search prices
7. Price matrix uses same quartile coloring as the existing search AirlineDateMatrix
8. Slide-over shows trip details, flight legs, hotel info, and chat thread
9. Chat thread shows full conversation history with system events
10. Status changes auto-post to chat
11. ActionBar shows pending items and collapses when empty
12. List view toggle available for traditional view preference
13. Mobile responsive
14. Feels like ONE unified surface
