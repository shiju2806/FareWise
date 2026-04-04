# FareWise — Product Documentation

## What FareWise Is

FareWise is a corporate travel booking platform that provides full transparency into travel spend — what was booked, what alternatives existed, what could have been saved, and why the traveler made the choice they did. AI powers the conversational interface and recommendation narratives, but the core value is accountability and informed decision-making.

---

## The Problem

Corporate travel is a $1.4 trillion global market. Studies consistently show 15-20% overspend vs optimal. For a company with 500 business travelers doing 4 trips/year at $3,000 average, that's $900K/year in recoverable savings.

The waste comes from three failures:

**1. Travelers lack context to choose well.**
Search "Toronto to London business class" and you get 50+ results. The traveler doesn't know the policy cap, can't compare date-shift savings, doesn't know a conference is inflating prices that week, and has no way to evaluate "is $3,694 a fair price for this route?" They pick the first reasonable option and move on.

**2. Managers approve without information.**
A manager sees "$3,694 for Air Canada business class — Approve?" They have no idea if that's the 20th percentile or the 80th. They don't know what cheaper alternatives the traveler was shown and declined. They don't know whether the company's travel policy was followed. They rubber-stamp it because investigating takes longer than the savings would justify.

**3. The organization has no memory.**
After the trip, nobody tracks what alternatives existed at booking time. Nobody knows if the traveler consistently picks premium options when cheaper equivalents are available. Nobody aggregates travel spend patterns across departments. Each trip is a standalone event with no institutional learning.

---

## Is This Product Actually Needed?

Honest answer: **Yes, but for a specific segment — and the pitch matters.**

### Who needs FareWise

**Mid-market companies (300-5,000 employees)** that:
- Spend $2M-$30M/year on travel — enough to justify optimization
- Don't have a dedicated TMC or full-time travel manager
- Have travel policies that exist on paper but aren't enforced at booking time
- Have managers approving trips with no context beyond the total cost
- Want visibility into travel spend without hiring a team to track it manually

This segment is genuinely underserved. Companies below 200 employees use Google Flights and expense reports — and that's fine for them. Companies above 5,000 have TMCs (CWT, Amex GBT, BCD Travel) with human agents and negotiated rates. The mid-market sits between these with painful options: Concur (terrible UX, low adoption), Navan (expensive), or nothing (shadow booking on consumer sites).

### Who doesn't need FareWise

- **Small companies (<200 employees):** The overhead of policy enforcement and approval workflows exceeds the savings. Google Flights + expense reports is sufficient.
- **Companies that don't fly much:** If travel is <2% of operating costs, the juice isn't worth the squeeze.
- **Companies with embedded TMCs:** If you already have BCD Travel managing your program with negotiated rates and dedicated agents, FareWise adds a layer without replacing the TMC.

### The honest competitive landscape

FareWise is not operating in a vacuum:
- **Navan** (valued at $9B+) has conversational booking and is adding AI features quarterly
- **Spotnana** is building AI-native corporate travel infrastructure
- **Concur** has the enterprise install base and brand trust
- **Google Flights / Skyscanner** are free and handle basic search excellently

FareWise's edge is not "we have AI" — everyone will have AI. The edge is the **transparency architecture**: the full audit trail that captures what alternatives existed, what the traveler saw, why they chose what they chose, and what the organization could have saved. This is the data that makes travel optimization measurable instead of theoretical.

---

## The Skyscanner / Google Flights Objection

> "We can just use Skyscanner. Why do we need FareWise?"

This is the right question. Here's the honest answer:

**Skyscanner is a search engine. FareWise is a decision engine with accountability.**

Skyscanner finds flights. FareWise finds flights, enforces policy, generates alternatives, calculates net savings (including hotel impact), explains the cost story to a manager, and creates a permanent audit trail of every decision.

### What consumer tools cannot do

| Capability | Skyscanner | FareWise |
|-----------|-----------|----------|
| Enforce corporate policy before booking | No | 8 configurable rule types with pass/warn/block |
| Manager approval with cost justification | No | Full narrative, alternatives snapshot, audit trail |
| "Book my family alongside my business trip" | No | Companion budgeting across cabins, same airline |
| Explain WHY a flight is the right choice | No | AI reasoning for every recommendation |
| Track what alternatives the traveler declined | No | Permanent snapshot at submission time |
| Filter red-eyes for business travelers automatically | Manual filter | Hard-excluded from results for premium cabins |
| Calculate hotel cost impact of date shifts | No | Net savings = flight savings minus hotel delta |
| Detect events inflating prices | No | PredictHQ integration with context |
| Compliance audit trail | No | Every action timestamped, every option recorded |
| Cost/convenience preference tracking | No | Per-leg slider position saved in audit trail |

**The fundamental difference**: Skyscanner optimizes for the individual's preferences. FareWise optimizes for the organization's constraints while respecting the individual's preferences. These are different problems.

But let's be honest about what Skyscanner does well: flight search, price comparison, date flexibility calendars, and multi-airline aggregation. FareWise doesn't need to beat Skyscanner at search — it needs to wrap search with policy, accountability, and transparency that consumer tools structurally cannot provide.

---

## Could This Be Built Without AI?

**The core value — transparency, policy enforcement, and accountability — could be built without AI.** Policy rules don't need LLMs. Savings calculations don't need LLMs. Approval workflows don't need LLMs. Audit trails don't need LLMs.

**But the product would be significantly worse in three specific ways.**

### What works without AI (and FareWise uses rules here intentionally)

| Component | Implementation | AI needed? |
|-----------|---------------|-----------|
| Flight search | DB1B + Amadeus API | No |
| Anchor selection | P40-P60 median, tier-based filtering | No |
| Flight scoring | Weighted composite (cost, time, stops, departure hour) | No |
| Alternative generation | 4-layer pipeline (same-day, routing, date-shift, cabin) | No |
| Trade-off scoring | 6-dimension weighted scoring with penalties | No |
| Policy enforcement | 8 rule types with configurable thresholds | No |
| Approval workflow | State machine with escalation | No |
| Savings calculation | Arithmetic on search results | No |
| Companion pricing | Parallel cabin searches, same-airline preference | No |
| Red-eye/work-hours filtering | Time-range checks, cabin-specific penalties | No |
| Event detection | PredictHQ API | No |
| Seasonality analysis | Amadeus Analytics API | No |

FareWise uses deterministic algorithms for all of the above. This is deliberate — rules are faster, cheaper, more predictable, and more auditable than LLM calls.

### What AI genuinely improves (and by how much)

#### 1. Trip creation: 30 seconds vs 3-5 minutes

Without AI: A form with 15+ fields. Origin, destination, departure date, return date, cabin, airline preference, passengers, flexibility, companions, companion cabin.

With AI: "Toronto to London mid April business round for a week, my partner and 2 kids are joining."

The LLM parses intent ("mid April" → April 13 Sunday, "for a week" → return April 19 Saturday, "my partner and 2 kids" → 3 companions, "round" → two legs). A regex parser handles "Toronto to London April 15" but breaks on "meeting in London next month" or "day trip to NYC" or "3-city Asia tour starting Tokyo."

**Why this matters for enterprise**: Adoption rate. The #1 reason corporate travel tools fail is traveler resistance to complex forms. When booking on the company tool is harder than booking on Google Flights, travelers book outside the system ("shadow booking"). Conversational booking removes the friction that causes policy leakage. It's not a gimmick — it's an adoption strategy.

#### 2. Alternative curation: 3-5 meaningful options vs 15 undifferentiated ones

The rule-based pipeline generates 15-20 candidates per leg across 4 layers. Without AI, you show "top 5 by savings" or dump all 15 on the traveler.

With AI, the LLM selects 3-5 that represent genuine tradeoffs and explains each:
- "Air Canada 1-stop via Montreal, $340 less — same airline, adds 2 hours"
- "WestJet direct, $520 less — different airline, similar schedule"
- "Depart Friday instead of Sunday, $280 less — saves a weekend day but adds hotel night (net: $180)"

The LLM ensures diversity (at least one same-airline, one cross-airline), filters inappropriate options (no red-eyes for business travelers, no budget carriers for premium cabins), and writes reasons humans can actually use to decide.

**Could you approximate this with rules?** Partially. You could hard-code "1 same-airline, 1 different airline, 1 date-shift, 1 routing change, 1 cabin downgrade" and generate template reasons. But the reasons would be mechanical ("$340 cheaper") instead of contextual ("same Air Canada service, 1 day earlier, saves $340"). And the selection logic can't express "this red-eye isn't worth $400 savings for a 7-hour transatlantic flight" without hundreds of rules.

#### 3. Approval narratives: 30-second decisions vs 10-minute investigations

Without AI, the manager sees a table: selected price, cheapest price, policy status. They either rubber-stamp or spend 10 minutes clicking through details.

With AI, the manager sees:
> "Sarah selected Air Canada business class YYZ-LHR at $3,694, positioned at the 45th percentile of available options. A $340 savings was available with a 1-stop routing. The selected fare is within policy limits."

This is the difference between "here's the data, figure it out" and "here's what happened, here's the context."

**Could you do this with templates?** For simple cases, yes: "Selected $X, cheapest was $Y, $Z premium." But templates can't handle companion travel narratives, near-miss budget situations, or multi-leg cost driver explanations. The LLM adapts to the specific trip context in ways that would require dozens of template branches.

### The honest assessment

**AI makes FareWise 3x better, but the core value proposition is deliverable without AI.**

A non-AI FareWise would be: a well-designed corporate travel tool with good search, transparent savings tracking, policy enforcement, and manager approval with full context. That's already better than what 80% of mid-market companies have today.

AI turns it from "better Concur" into "travel advisor in software." The conversational interface drives adoption. The curation intelligence drives better decisions. The narratives drive faster approvals. But if you stripped the AI and kept the transparency architecture, you'd still have a useful product.

**The AI is the moat, not the foundation.** The foundation is transparency. The AI makes it hard for someone to clone the transparency features and match the experience.

---

## What the Product Actually Does (Feature by Feature)

### 1. Conversational Trip Planning

The chat interface (powered by gpt-4o with tool calling) understands:
- Vague dates: "mid April" → April 15, flexibility ±5 days
- Corporate day rules: auto-shifts to Sunday outbound, Saturday return
- Round-trip inference: always two legs unless "one-way" is explicit
- Companion detection: "my wife and 2 kids" → 3 companions, triggers budget flow
- Airline preference: asks about loyalty programs for business/first class
- Meeting awareness: "meeting on April 15" → arrive April 14, return April 16
- Multi-city: "Tokyo, then Seoul, then home" → 3 sequential legs

The coordinator uses tool calling to trigger actions (search, budget calculation, completion) — the LLM decides flow, not hardcoded if/else gates. Every LLM decision has a safety net: if the LLM doesn't trigger search when it should, the coordinator auto-triggers it.

### 2. Smart Anchor Selection (Rule-Based)

The anchor flight sets the budget envelope. FareWise uses P40-P60 median pricing, not cheapest, because:
- Cheapest is often a 2am red-eye with 3 stops on a budget carrier
- P40-P60 median represents what a knowledgeable travel manager would approve
- This makes savings calculations honest — "you saved $X vs a reasonable baseline," not "you saved $X vs an unrealistic floor"

Selection tiers (in priority order):
1. Preferred airline, direct flight
2. Any airline, direct flight
3. 1-stop via carrier hub
4. Any 1-stop flight

Departures before 6am and after 10pm are filtered out.

### 3. Four-Layer Alternative Generation (Rule-Based)

| Layer | What Changes | Min Savings | Max | Example |
|-------|-------------|-------------|-----|---------|
| Same-day swap | Airline | $50 | 3 | WestJet instead of Air Canada |
| Routing change | Stops | $100 | 2 | Same airline, 1-stop via hub |
| Date shift | Travel dates | $100 | 4 | Friday instead of Sunday, with hotel impact |
| Cabin downgrade | Cabin class | $200 | 2 | Premium Economy instead of Business |

Trip-window proposals search ±60 days for optimal date combinations, respecting corporate day rules (outbound Fri/Sat/Sun, return Fri/Sat), trip duration constraints (±2 days, minimum 3 days), and hotel cost impact.

### 4. Trade-Off Scoring (Rule-Based)

Every alternative is scored on weighted dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Net Savings | 60 | Flight savings minus hotel cost impact |
| Traveler Preference | 70 | Airline loyalty scoring (user's airline: 1.0, alliance: 0.8, low-cost: 0.15) |
| Disruption | 40 | Schedule change impact |
| Sustainability | 10 | Fewer stops = lower emissions |

Protections built into scoring:
- **Red-eye hard exclusion**: Business/first travelers never see 11pm-6am departures
- **Red-eye penalty**: Economy travelers see them with 30% score reduction
- **Work-hours penalty**: Mon-Thu 9am-5pm departures penalized (loses a work day)
- **Tier filtering**: Premium cabin travelers only see full-service airlines
- **Corporate-friendly boost**: Friday evening and Saturday departures get 20-30% boost

### 5. AI-Powered Curation (TravelAdvisor)

After rule-based scoring narrows the field, the LLM (gpt-4o-mini) selects the final 3-5 alternatives per leg with:
- Human-readable reason for each (under 20 words)
- Trip-level recommendation: approve / review / optimize
- Key insight (most actionable optimization)
- Manager narrative (3-4 factual sentences)
- Justification prompt (if cost exceeds thresholds)

Safety guarantees enforced after LLM output:
- At least 1 same-airline alternative per leg
- At least 1 different-airline alternative for comparison
- Maximum 5 per leg

Fallback: If LLM fails, rule-based reasons and narratives are generated. The product always works.

### 6. Companion Travel Budgeting

No consumer tool or traditional TMC handles this natively.

Flow:
1. Chat asks "How many companions?" → "Same dates or different?"
2. Parallel search: 3 cabins (business, premium economy, economy) x N legs
3. Same-airline preference: shows prices for the employee's airline first
4. AI advisor recommends optimal cabin with reasoning
5. Near-miss detection: "Business is only $200 over budget — worth an exception?"
6. Full audit trail: companion pricing snapshot persisted permanently

### 7. Policy Engine (Rule-Based)

Eight configurable rules, each returning pass / warn / block:

| Rule | Example |
|------|---------|
| Max Price | Business class max $5,000 per leg |
| Advance Booking | Must book 14+ days before departure |
| Cabin Restriction | Economy only for flights under 6 hours |
| Preferred Airline | "Company prefers Air Canada" (info only) |
| Max Stops | Direct flights only for business class |
| Passenger Cabin | 4+ passengers → economy only |
| Approval Threshold | Trips under $3,000 auto-approve |
| Cabin Class Count | Max 2 legs in business per trip |

Supports role-based exceptions, currency conversion, and route-type conditions.

### 8. Approval Workflow

**What the manager sees:**
- Cost positioning (selected vs cheapest vs most expensive, with visual bar)
- AI-generated narrative explaining the cost story
- Every alternative the traveler was shown but didn't pick
- All policy evaluations with pass/warn/block status
- Per-leg breakdown with airline, price, and justification
- Companion pricing breakdown (if applicable)
- Events affecting prices during travel dates
- Traveler's cost/convenience slider positions
- Complete activity timeline

**Manager actions:** Approve, Reject, Request Changes, Escalate, Comment.

### 9. Compliance Audit Trail

Every trip submission permanently captures:
- All flight options shown to the traveler
- All alternatives (same-day, date-shift, routing, cabin) considered
- Traveler's cost/convenience slider position per leg
- Policy evaluation results with specific violation details
- Traveler's justification text for policy overrides
- Companion pricing breakdown and combined costs
- Manager's decision with comments and timestamps
- Full activity history (created → commented → approved/rejected/escalated)

This is the data an internal audit team needs. No consumer tool provides it. Most TMC tools provide partial versions.

### 10. Event and Seasonality Awareness

**PredictHQ**: Conferences, sports events, festivals near destination (rank 55+, 50km radius). Explains price spikes — "SXSW is happening during your travel dates."

**Amadeus Analytics**: Route-level seasonality (peak/shoulder/off-peak months). A flight that looks expensive in absolute terms may be cheap for peak season.

Both signals feed into the price advisor and appear in the savings report for manager context.

---

## Architecture: AI vs Rules

```
User Input (natural language)
    │
    ▼
┌─────────────────────────────┐
│  LAYER 3: AI                │
│  TripCoordinator (gpt-4o)   │ ← Conversational planning
│  TravelAdvisor (gpt-4o-mini)│ ← Alternative curation + narrative
│  CompanionAdvisor (gpt-4o-mini) ← Cabin budget reasoning
│  PriceAdvisor (gpt-4o-mini) │ ← Book/wait/watch synthesis
│  Every call has a fallback   │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  LAYER 2: RULES             │
│  AnchorSelector (P40-P60)   │ ← Budget baseline
│  FlightAlternatives (4-layer)│ ← Candidate generation
│  TradeOffResolver (scoring)  │ ← Multi-dimensional ranking
│  ScoringEngine (slider)      │ ← User preference weighting
│  PolicyEngine (8 rules)      │ ← Compliance enforcement
│  ApprovalService (workflow)  │ ← State machine + audit trail
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  LAYER 1: DATA              │
│  Amadeus (live flights)      │
│  DB1B (historical fares)     │
│  PredictHQ (events)          │
│  Amadeus Analytics (season)  │
└─────────────────────────────┘
```

**Design principle**: AI for reasoning and communication. Rules for enforcement, scoring, and search. Every LLM call has a deterministic fallback — if the AI provider goes down, the product degrades gracefully but continues working.

**LLM calls per trip**: 5-10 (depends on conversation length and number of legs).

**Models**: OpenAI gpt-4o (planning), gpt-4o-mini (advisory), Claude claude-sonnet-4-5 (fallback). All configurable in `recommendation/config.py`.

---

## The Core Value Proposition

The strongest argument for FareWise is not "we use AI."

**It's: "After every trip booking, the company knows exactly what it spent, what it could have spent, and why the traveler made the choice they did."**

No consumer tool provides this. Most enterprise tools provide fragments of it. FareWise makes travel spend a transparent, auditable, informed decision — not a black box between the traveler's credit card and the expense report.

AI makes the experience faster (conversational booking), smarter (curated alternatives with reasoning), and clearer (narrative explanations for managers). But the transparency architecture — the full audit trail with alternatives snapshot, policy evaluations, cost driver analysis, and companion pricing — is the foundation that makes FareWise worth deploying.

The AI is the moat. The transparency is the product.

---

*Last updated: April 2026*
