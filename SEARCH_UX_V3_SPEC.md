# Search UX v3 — Competitive-Inspired Upgrades

**Created:** 2026-02-12
**Status:** Proposed
**Based on:** Competitive analysis of Navan, SAP Concur, Google Flights, Skyscanner, Kayak, TravelPerk, Brex Travel

---

## Current State (Search Experience v2 — shipped)

What's already implemented in the search flow:

- Airline x Date price matrix with green/amber/red quartile coloring
- Compact flight rows (~52px) with airline color circles, badges, price pills
- Collapsible price advisor banner
- Tiered justification: inline banner ($100-$500), full modal (>$500) with preset chips + comparison table
- ±7 day search on primary airport pair, within_flexibility tagging
- Calendar <-> matrix date linking (selectedDate + preferredDate column highlights)
- Color-coded price badges throughout (quartile-based)
- Enhanced selection bar with savings context
- Skeleton loading states for all sections

**Files involved:**
- `frontend/src/pages/TripSearch.tsx` — main search page
- `frontend/src/components/search/SearchResults.tsx` — layout orchestrator
- `frontend/src/components/search/FlightOptionCard.tsx` — compact flight rows
- `frontend/src/components/search/AirlineDateMatrix.tsx` — price matrix
- `frontend/src/components/search/PriceAdvisorPanel.tsx` — collapsible advisor
- `frontend/src/components/search/JustificationModal.tsx` — tiered justification
- `frontend/src/components/search/MonthCalendar.tsx` — price calendar
- `frontend/src/components/search/WhatIfSlider.tsx` — cost/time slider
- `backend/app/services/search_orchestrator.py` — search backend
- `backend/app/services/justification_service.py` — LLM justification prompts
- `backend/app/services/price_advisor_service.py` — price intelligence

---

## Upgrade 1: Best / Cheapest / Fastest Sort Tabs

**Inspiration:** Skyscanner

**What:** Three prominent tab buttons above the flight list that instantly re-sort results. Currently flights are sorted by score (from the backend slider). Users have no way to quickly sort by price or duration.

**Behavior:**
- **Best** (default): sorted by `score` field (existing AI recommendation score from slider)
- **Cheapest**: sorted by `price` ascending
- **Fastest**: sorted by `duration_minutes` ascending

**UI:**
```
┌──────────┬───────────┬───────────┐
│  Best    │ Cheapest  │  Fastest  │
│  ●       │  $1,548   │  8h 20m   │
└──────────┴───────────┴───────────┘
```
- Active tab: `bg-primary text-primary-foreground`
- Inactive tabs: `bg-secondary text-secondary-foreground`
- Below each label, show the best value for that sort (e.g., cheapest price, shortest duration)
- Sorting is client-side only — no API call needed

**File:** `frontend/src/components/search/SearchResults.tsx`

**Changes:**
- Add `sortMode` state: `"best" | "cheapest" | "fastest"`
- Sort `filteredOptions` based on `sortMode` before slicing for display
- Render three tab buttons above the flight list section (between airline filter chips and flight list header)

**Effort:** Small — pure frontend, ~30 lines

---

## Upgrade 2: Policy Compliance Badge per Flight Row

**Inspiration:** SAP Concur (traffic light icons on every fare option — industry standard for corporate travel)

**What:** Every flight row shows a small icon indicating policy compliance status. This is the single most important corporate travel UX pattern that FareWise is missing.

**Visual:**
- Green checkmark: in-policy (price within threshold, allowed airline, allowed cabin)
- Yellow triangle: warning (above soft limit, or flexibility exception)
- Red circle-X: violation (above hard limit, blocked airline, restricted cabin)
- No icon: no policy configured for this category

**How it works:**

The backend already has a full policy engine (`backend/app/services/policy_engine.py`) that evaluates selections. But it only runs at selection time (when you click Confirm). For this feature, we need lightweight per-flight policy evaluation at search time.

### Backend changes

**File:** `backend/app/routers/search.py`

Add a new endpoint or extend the search response:

**Option A (preferred): Inline in search response**

After scoring flights, run a lightweight policy check on each flight option and include a `policy_status` field in the response:

```python
# In search_orchestrator.py, after scoring
for flight in all_options:
    flight["policy_status"] = "pass"  # default
    flight["policy_notes"] = []

    # Check max_price policies
    if flight["price"] > max_price_threshold:
        flight["policy_status"] = "block" if action == "block" else "warn"
        flight["policy_notes"].append(f"Exceeds ${max_price_threshold} limit")

    # Check cabin_restriction policies
    if flight["cabin_class"] and cabin_not_allowed(flight["cabin_class"]):
        flight["policy_status"] = "block"
        flight["policy_notes"].append(f"{flight['cabin_class']} not permitted")

    # Check preferred_airline policies
    if airline_not_preferred(flight["airline_code"]):
        if preferred_action == "warn":
            flight["policy_status"] = max(flight["policy_status"], "warn")
            flight["policy_notes"].append("Non-preferred airline")
```

This should use the existing `PolicyService` / policy evaluation logic but in a simplified per-flight mode (not the full trip-level evaluation).

### Frontend changes

**File:** `frontend/src/types/flight.ts`

Add to `FlightOption`:
```typescript
policy_status?: "pass" | "warn" | "block";
policy_notes?: string[];
```

**File:** `frontend/src/components/search/FlightOptionCard.tsx`

Add a policy badge in the badges section:
- `pass`: small green checkmark circle (`bg-emerald-100 text-emerald-600`)
- `warn`: small yellow triangle (`bg-amber-100 text-amber-600`)
- `block`: small red X circle (`bg-red-100 text-red-600`)
- Tooltip on hover shows `policy_notes` joined

**File:** `frontend/src/components/search/AirlineDateMatrix.tsx`

In matrix cells, show a tiny dot overlay for policy status (optional, may be too busy).

**Effort:** Medium — needs backend policy integration with search results

---

## Upgrade 3: Price Insights Gauge Bar

**Inspiration:** Google Flights (green/yellow/red horizontal bar showing Low/Typical/High)

**What:** Replace the text-based price assessment in `PriceAdvisorPanel` with a visual gauge bar. The advisor already has `confidence`, `assessment` ("good_deal", "fair_price", "above_average", "wait_if_flexible"), and price range data. This upgrade makes it visual.

**Visual:**
```
Price for this route
├── Green zone ──┤── Yellow zone ──┤── Red zone ──┤
                 ▲
            Your price: $1,768

Low ($1,548)          Typical ($2,800)         High ($10,344)
```

- Horizontal bar with three color zones (emerald → amber → red gradient)
- A marker/arrow showing where the current best price falls
- Labels: "Low", "Typical", "High" with dollar amounts
- Below: one-line verdict — "Prices are low for this route. Book now." or "Prices are above average. Consider waiting."

**Implementation:**

**File:** `frontend/src/components/search/PriceAdvisorPanel.tsx`

The panel already fetches advisor data with `price_range: { low, typical, high }` and `assessment`. Replace the expanded content's first section with a gauge bar component.

```tsx
function PriceGauge({ low, typical, high, current }: { low: number; typical: number; high: number; current: number }) {
  // Calculate position of current price as percentage along the bar
  const range = high - low;
  const pct = range > 0 ? Math.min(100, Math.max(0, ((current - low) / range) * 100)) : 50;

  return (
    <div className="space-y-1">
      {/* Gradient bar */}
      <div className="relative h-3 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-400">
        {/* Current price marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-foreground shadow-md"
          style={{ left: `${pct}%` }}
        />
      </div>
      {/* Labels */}
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>Low (${low.toLocaleString()})</span>
        <span>Typical (${typical.toLocaleString()})</span>
        <span>High (${high.toLocaleString()})</span>
      </div>
    </div>
  );
}
```

Keep the collapsible behavior. The gauge shows in collapsed state (replacing or alongside the headline text). Full details remain in expanded state.

**Effort:** Small — frontend-only, advisor data already available

---

## Upgrade 4: Dynamic Budget Percentage in Justification

**Inspiration:** TravelPerk ("Your selection is 143% of cheapest. Policy allows up to 120%.")

**What:** Show the selection's cost as a percentage of the cheapest available option, alongside the policy threshold. Much clearer than raw dollar amounts for routes with varying price ranges.

**Where it appears:**
1. In the selection bar (bottom bar when a flight is selected)
2. In the justification modal/banner
3. In the approval review card

**Example:**
```
Selected: Turkish TK18 · $3,777
214% of cheapest (Icelandair $1,768) · Policy allows up to 150%
```

**Implementation:**

### Selection bar (TripSearch.tsx)

After `analyze-selection` returns, compute and display:
```
const pctOfCheapest = Math.round((selectedPrice / cheapestPrice) * 100);
```

Show as: `"{pctOfCheapest}% of cheapest · Policy allows up to {policyPct}%"`

Color: green if within policy threshold, amber if 100-150% of threshold, red if >150%.

### Justification modal (JustificationModal.tsx)

Add a percentage bar below the savings badge:
```
┌─────────────────────────────────┐
│ ████████████████░░░░░░░░        │  214% of cheapest
│                 ↑               │  Policy: 150%
│           policy limit          │
└─────────────────────────────────┘
```

### Backend

**File:** `backend/app/routers/search.py` (analyze-selection endpoint)

Add to the response:
```python
"budget_context": {
    "percent_of_cheapest": round((selected_price / cheapest_price) * 100),
    "policy_threshold_percent": 150,  # from active max_price policy, or null
    "within_policy": percent_of_cheapest <= policy_threshold_percent,
}
```

The policy threshold percentage comes from active `max_price` policies. If the policy uses a fixed dollar amount, convert: `threshold_pct = round((policy_max / cheapest_price) * 100)`. If no policy exists, `policy_threshold_percent` is null and the percentage bar is hidden.

**Effort:** Medium — backend policy lookup + frontend display

---

## Upgrade 5: Calendar + Bar Chart Toggle

**Inspiration:** Skyscanner (toggle between calendar grid and bar chart view of the same data)

**What:** Add a small toggle in the calendar section header to switch between the existing month grid view and a vertical bar chart showing prices per date. Same data, different visual — some users prefer the at-a-glance bar chart.

**Bar chart layout:**
```
$3,500 ┤
$3,000 ┤          ██
$2,500 ┤    ██    ██    ██
$2,000 ┤    ██    ██    ██    ██
$1,500 ┤ ██ ██ ██ ██    ██ ██ ██
       └──┬──┬──┬──┬──┬──┬──┬──┬──
         Jul Jul Jul Jul Jul Jul Jul
         10  11  12  13  14  15  16
```

- Bars colored by quartile (green/amber/red)
- Selected date bar highlighted with primary ring
- Preferred date bar has a small star/dot marker
- Click a bar to select that date (same as clicking calendar cell)
- Horizontal scroll for many dates

**Implementation:**

**New file:** `frontend/src/components/search/PriceBarChart.tsx`

Props: same as MonthCalendar (dates, prices, selectedDate, onDateSelect, preferredDate)

Uses CSS grid or flexbox — no charting library needed:
```tsx
// Each bar is a div with dynamic height
<div
  className="bg-emerald-400 rounded-t"
  style={{ height: `${(price / maxPrice) * 120}px` }}
/>
```

**File:** `frontend/src/components/search/SearchResults.tsx`

Add a view toggle state: `calendarView: "calendar" | "chart"`

In the calendar section, render either `<MonthCalendar>` or `<PriceBarChart>` based on toggle. Toggle button is a small icon pair (grid icon / bar-chart icon) in the section header.

**Effort:** Medium — new component, but simple div-based bars (no library)

---

## Upgrade 6: Auto-Approve for Compliant Trips

**Inspiration:** TravelPerk (95%+ compliance rate by removing friction for in-policy bookings)

**What:** When a trip is submitted and ALL legs pass policy evaluation with zero warnings or violations, skip the manager approval step entirely. Mark the trip as `approved` immediately with `approved_by: "auto"`.

**Why:** Reduces turnaround time from hours/days to instant. Managers only review exceptions. Dramatically improves user experience for compliant travelers.

**Implementation:**

**File:** `backend/app/services/approval_service.py`

In the `submit_trip()` or `create_approval()` flow:

```python
# After policy evaluation
if all(check["status"] == "pass" for check in policy_checks):
    # Auto-approve: no manager review needed
    approval.status = "approved"
    approval.decided_at = datetime.utcnow()
    approval.decided_by = "auto-policy"
    approval.decision_note = "All legs within policy — auto-approved"
    trip.status = "approved"
    trip.approved_at = datetime.utcnow()
    # Still send notification to traveler
    await notification_service.send("trip_approved", user_id=trip.user_id, ...)
    # Skip sending approval_requested to manager
else:
    # Existing flow: create pending approval, notify manager
    ...
```

**File:** `backend/app/models/policy.py` or config

Add a setting: `auto_approve_compliant: bool = True` (can be toggled by admin).

**Frontend:** No changes needed — the trip status updates to `approved` immediately. The My Trips page already handles `approved` status with the green badge.

**Audit trail:** Log an audit event `trip_auto_approved` with details showing which policies were checked.

**Effort:** Small-Medium — backend logic change, no frontend changes

---

## Upgrade 7: Reward Incentive Display

**Inspiration:** Navan ("Book this and earn $X in personal travel credit")

**What:** When a cheaper option exists, show a positive incentive message alongside the savings context. Instead of only "This costs $2,009 more than cheapest" (punitive framing), also show "Switch to Icelandair and earn a $50 travel reward" (positive framing).

**Where:**
- Selection bar: below the savings context line
- Justification modal: on each alternative card
- Flight list: on the recommended/cheapest flight row

**Example in selection bar:**
```
Selected: Turkish TK18 · $3,777
$2,009 more than cheapest (Icelandair $1,768)
💡 Switch and earn $50 personal travel credit
```

**Implementation:**

### Backend

**File:** `backend/app/services/reward_service.py` (new)

Simple reward calculation:
```python
def calculate_reward(savings_amount: float) -> float:
    """Reward = 5% of savings, capped at $100"""
    if savings_amount <= 0:
        return 0
    return min(savings_amount * 0.05, 100)
```

Add `reward_amount` to the `analyze-selection` response.

### Config

Add to company settings (or hardcode initially):
- `reward_percent`: 5 (percentage of savings given as reward)
- `reward_cap`: 100 (max reward per trip)
- `reward_enabled`: true/false

### Frontend

**File:** `frontend/src/pages/TripSearch.tsx`

In the selection bar, if `justificationAnalysis.reward_amount > 0`:
```tsx
<span className="text-xs text-emerald-600 font-medium">
  Switch to save and earn ${reward_amount} travel credit
</span>
```

**File:** `frontend/src/components/search/JustificationModal.tsx`

On each alternative card, show reward amount if switching.

**Effort:** Medium — new service + frontend integration. Reward redemption/tracking is a future feature; this phase only shows the incentive.

---

## Upgrade 8: Fare Inclusion Icons

**Inspiration:** Google Flights, SAP Concur

**What:** Small icons on each flight row showing what's included: carry-on bag, checked bag, seat selection, changeable ticket. Prevents post-booking surprises and reduces justification friction ("I picked the more expensive flight because it includes bags").

**Icons (4 total):**
- Carry-on bag: small bag icon (always or never, based on fare)
- Checked bag: suitcase icon (included / not included / paid)
- Seat selection: seat icon (included / not included)
- Changeable: circular arrow icon (free change / fee / non-changeable)

**Challenge:** Google Flights / fast_flights may not return fare inclusion data. This depends on the data source.

**Implementation:**

### Step 1: Check data availability

**File:** `backend/app/services/flight_search/google_flights_client.py`

Check if the Google Flights protobuf response includes baggage/fare details. If not, this upgrade is deferred until a data source provides it.

### Step 2: If data available

**File:** `frontend/src/types/flight.ts`

Add optional fields:
```typescript
baggage_included?: "carry_on" | "checked" | "none";
changeable?: boolean;
```

**File:** `frontend/src/components/search/FlightOptionCard.tsx`

Add a small icon row between the duration/stops section and the price badge:
```tsx
<div className="flex items-center gap-1 text-muted-foreground">
  {flight.baggage_included === "checked" && <BagIcon className="w-3 h-3" />}
  {flight.changeable && <ChangeIcon className="w-3 h-3" />}
</div>
```

Use simple SVG inline icons (no icon library needed).

**Effort:** Depends on data availability. If data exists: Small. If not: Deferred.

---

## Implementation Priority

```
Priority 1 (Quick Wins — frontend only, < 1 hour each)
├── Upgrade 1: Sort tabs (Best/Cheapest/Fastest)
└── Upgrade 3: Price insights gauge bar

Priority 2 (Medium effort — backend + frontend, 1-3 hours each)
├── Upgrade 4: Dynamic budget percentage in justification
├── Upgrade 5: Calendar + bar chart toggle
└── Upgrade 6: Auto-approve for compliant trips

Priority 3 (Larger effort — new services or data dependencies)
├── Upgrade 2: Policy compliance badges per flight row
├── Upgrade 7: Reward incentive display
└── Upgrade 8: Fare inclusion icons (data-dependent)
```

---

## Files Summary

| File | Change |
|------|--------|
| `frontend/src/components/search/SearchResults.tsx` | Sort tabs, calendar view toggle |
| `frontend/src/components/search/FlightOptionCard.tsx` | Policy badge, fare icons |
| `frontend/src/components/search/PriceAdvisorPanel.tsx` | Gauge bar visualization |
| `frontend/src/components/search/PriceBarChart.tsx` | **NEW** — bar chart view of prices |
| `frontend/src/components/search/JustificationModal.tsx` | Budget %, reward display |
| `frontend/src/pages/TripSearch.tsx` | Budget %, reward in selection bar |
| `frontend/src/types/flight.ts` | policy_status, policy_notes, baggage fields |
| `backend/app/services/search_orchestrator.py` | Inline policy check per flight |
| `backend/app/routers/search.py` | budget_context in analyze-selection response |
| `backend/app/services/approval_service.py` | Auto-approve logic |
| `backend/app/services/reward_service.py` | **NEW** — reward calculation |

**Total: 9 files modified, 2 new files**

---

## Competitive Reference

| Pattern | Used by | FareWise status |
|---------|---------|----------------|
| Airline x Date matrix | Google Flights | Shipped |
| Green/amber/red price coloring | Skyscanner, Google | Shipped |
| Tiered justification + presets | FareWise original | Shipped |
| Savings narrative on approvals | FareWise original | Shipped |
| Best/Cheapest/Fastest tabs | Skyscanner | **Proposed (Upgrade 1)** |
| Policy traffic light per flight | SAP Concur | **Proposed (Upgrade 2)** |
| Price insights gauge bar | Google Flights | **Proposed (Upgrade 3)** |
| Dynamic budget % | TravelPerk | **Proposed (Upgrade 4)** |
| Calendar + bar chart toggle | Skyscanner | **Proposed (Upgrade 5)** |
| Auto-approve compliant trips | TravelPerk | **Proposed (Upgrade 6)** |
| Reward incentive display | Navan | **Proposed (Upgrade 7)** |
| Fare inclusion icons | Google, Concur | **Proposed (Upgrade 8)** |
| Carbon emissions per flight | Concur, Skyscanner | Future |
| On-time performance | Concur | Future |
| Re-book from past trips | Navan | Future |
| Approve from Slack | TravelPerk | Future |
| Auto-cancel timer | Brex | Future |
| Explore map with budget | Kayak | Future |
