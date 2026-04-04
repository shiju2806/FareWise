"""TripCoordinator — thin executor for LLM-planned trip actions.

The LLM decides what to do (via tool calls). The coordinator just runs it.
Zero business logic — flow control lives in the LLM, not in if/else gates.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

from app.services.llm_client import llm_client
from app.services.agents.base import AgentResponse
from app.services.agents.conversation_state import ConversationState, LegState

logger = logging.getLogger(__name__)

_AGENT_TIMEOUT = 25.0
_MAX_HISTORY_MSGS = 20

# ------------------------------------------------------------------
# System prompt — domain rules only, no extraction rules the LLM knows
# ------------------------------------------------------------------

TRIP_SYSTEM_PROMPT = """\
You are a friendly travel planning assistant for a corporate travel tool.
Today is {today}. The current year is {year}.

Your job: help the user plan a trip through brief conversation, then trigger
actions (search, budget, complete) at the right time using tools.

CRITICAL TOOL BEHAVIOR:
- You MUST call update_trip AND at least one more tool (ask_user, search_flights,
  or mark_complete) in EVERY response. Never call update_trip alone.
- Since your text content may not reach the user, ALWAYS use ask_user to
  communicate with the user. Put your full reply in the ask_user "question" field.
- You must call ALL necessary tools in a SINGLE response, not across multiple turns.

RULES:
1. Be decisive. When the user provides origin, destination, and rough timeframe,
   fill in sensible defaults and call update_trip immediately.
2. This is a CORPORATE tool. All trips are business trips regardless of cabin class.
3. Date logic for vague dates:
   - "Mid [month]" -> 15th, flexibility_days=5
   - "Early [month]" -> 3rd, flexibility_days=4
   - "Late [month]" / "End of [month]" -> 25th, flexibility_days=4
   - "Next week" -> Monday of next week, flexibility_days=3
   - Specific date ("April 15") -> use as-is, flexibility_days=3
   Shift vague dates to nearest Sunday ON OR BEFORE the anchor so the traveler
   arrives Monday. Note the shift in your reply.
4. Round trips: ALWAYS create TWO legs (outbound + return) unless the user
   explicitly says "one-way". If no return date given, default to 5 working
   days later (Mon-Fri), return Saturday. Example: depart Sun Apr 12 →
   return Sat Apr 18. You MUST include BOTH legs in update_trip.
5. For business/first class WITHOUT an airline preference mentioned:
   call update_trip (with BOTH legs), then ask_user to ask about preferred
   airline or loyalty program. Do NOT search yet.
6. For business/first class WITH an airline preference (or user said "no
   preference"): call update_trip then search_flights immediately.
7. When calling search_flights (ANY cabin class), ALSO call ask_user
   with block_type="companion_prompt" in the SAME response to ask about
   companions — UNLESS the user already mentioned companions or has been
   asked before (companions asked=true in state).
7b. After companions are confirmed (count > 0) and dates_asked=false in state,
   ask about travel dates using ask_user with block_type="companion_dates_prompt".
   Also call update_trip with companions_same_dates=true or false based on the
   user's answer. This determines if companions fly on the same dates or different.
8. CRITICAL: Only update fields the user actually mentioned. If the user says
   "Air Canada" answering an airline question, update preferred_airline ONLY.
   Do NOT infer companions_count from that answer. Do NOT change fields the
   user did not address.
9. Economy/premium_economy with complete legs AND companions resolved (count=0
   or budget_calculated): call update_trip then mark_complete. Do NOT mark
   complete if companions are unknown (count=-1) — ask about companions first.
10. "meeting on [date]" -> arrive day before, return day after.
11. "day trip" / "same day return" -> two legs, same date, flexibility_days=0.
12. Multi-city -> create sequential legs, 2-3 days per city.
13. Use the PRIMARY airport IATA code for each city: Toronto=YYZ, London=LHR,
    New York=JFK, Paris=CDG, Chicago=ORD, Los Angeles=LAX, Vancouver=YVR,
    Montreal=YUL, Washington=IAD, San Francisco=SFO. Never use city codes
    like LON, NYC, etc.

TOOL CALLING ORDER:
- Always call update_trip FIRST to persist extracted info before other actions.
- search_flights requires legs with airports + dates set, cabin = business/first.
- calculate_budget requires companions_count > 0. Call it alongside search_flights
  when companions are known — tools execute sequentially so search completes first.
- mark_complete is the final action when the trip is fully resolved.
- You may call multiple tools in one response. They execute in order.
- ONE-SHOT EXAMPLE: if the user says "Toronto to London business Air Canada with
  my wife and 2 kids", call: update_trip (legs + companions_count=3) → search_flights
  → calculate_budget → mark_complete. All in ONE response. Do NOT ask about companions
  when the user already mentioned them in their message.

CURRENT TRIP STATE:
{current_state}"""

# ------------------------------------------------------------------
# Tool definitions — the LLM's action vocabulary
# ------------------------------------------------------------------

TRIP_TOOLS = [
    {
        "name": "update_trip",
        "description": (
            "Update the trip state with extracted information. Call this whenever "
            "the user provides route, date, cabin, airline, or companion info. "
            "Always include ALL legs (not just changed ones) to avoid data loss."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "legs": {
                    "type": "array",
                    "description": "All trip legs. Include every leg, not just changed ones.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sequence": {"type": "integer"},
                            "origin_city": {"type": "string"},
                            "origin_airport": {"type": "string", "description": "IATA code"},
                            "destination_city": {"type": "string"},
                            "destination_airport": {"type": "string", "description": "IATA code"},
                            "preferred_date": {"type": "string", "format": "date"},
                            "flexibility_days": {"type": "integer"},
                            "cabin_class": {
                                "type": "string",
                                "enum": ["economy", "premium_economy", "business", "first"],
                            },
                            "passengers": {"type": "integer"},
                            "preferred_airline": {
                                "type": "string",
                                "description": "IATA code or empty string for no preference",
                            },
                        },
                    },
                },
                "companions_count": {
                    "type": "integer",
                    "description": (
                        "Number of companions. -1 = unknown (user hasn't mentioned), "
                        "0 = solo (user explicitly confirmed), 1+ = companion count. "
                        "Only change this when the user explicitly mentions companions."
                    ),
                },
                "companions_same_dates": {
                    "type": "boolean",
                    "description": (
                        "True if companions travel on the same dates as the employee, "
                        "false if they have different travel dates. Only set when the "
                        "user explicitly answers the companion dates question."
                    ),
                },
                "confidence": {"type": "number"},
                "interpretation_notes": {"type": "string"},
            },
        },
    },
    {
        "name": "search_flights",
        "description": (
            "Search for flights on all trip legs. Call ONLY when all legs have "
            "origin_airport, destination_airport, and preferred_date set AND cabin "
            "is business or first AND legs have NOT already been searched "
            "(no [SEARCHED] marker in state)."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "calculate_budget",
        "description": (
            "Calculate cabin budget options for companion travel. Call ONLY when "
            "flights have been searched (legs show [SEARCHED]) AND companions_count "
            "is greater than 0 AND budget has NOT already been calculated."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the user a question when you need information you cannot infer. "
            "Set block_type to 'companion_prompt' for companion picker, "
            "'companion_dates_prompt' for date preference question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user.",
                },
                "block_type": {
                    "type": "string",
                    "enum": ["companion_prompt", "companion_dates_prompt", "text"],
                    "description": (
                        "'companion_prompt' shows structured companion picker. "
                        "'companion_dates_prompt' shows same/different dates picker. "
                        "'text' is a plain question."
                    ),
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "mark_complete",
        "description": (
            "Mark the trip as ready. Call when: "
            "(a) economy/premium_economy + solo (companions_count=0): after update_trip. "
            "(b) business/first + solo: when user says 'just me'/'solo', call update_trip "
            "with companions_count=0 AND mark_complete in the same response. "
            "(c) any cabin + companions: after calculate_budget completes. "
            "Do NOT call mark_complete if companions_count is -1 (unknown)."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
]


# ------------------------------------------------------------------
# Coordinator — thin executor
# ------------------------------------------------------------------

class TripCoordinator:
    """Thin executor: LLM decides what to do, coordinator runs it."""

    async def process(
        self,
        user_message: str,
        state: ConversationState,
        conversation_history: list[dict],
    ) -> AgentResponse:
        request_start = time.perf_counter()
        trimmed = self._trim_history(conversation_history, state)

        today = date.today()
        system = TRIP_SYSTEM_PROMPT.format(
            today=today.isoformat(),
            year=today.year,
            current_state=state.to_llm_context(),
        )

        msgs = list(trimmed)
        msgs.append({"role": "user", "content": user_message})

        # Single LLM call — returns reply text + tool calls
        try:
            result = await asyncio.wait_for(
                llm_client.complete_with_tools(
                    system=system,
                    user="",
                    messages=msgs,
                    tools=TRIP_TOOLS,
                    max_tokens=1500,
                    temperature=0,
                    model="gpt-4o",
                    tool_choice="required",
                ),
                timeout=_AGENT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("LLM timed out after %.0fs", _AGENT_TIMEOUT)
            return AgentResponse(
                content="That's taking longer than expected. Please try again.",
                state=state,
            )
        except Exception as e:
            logger.error("LLM call failed: %s", e, exc_info=True)
            return AgentResponse(
                content="Something went wrong. Could you rephrase that?",
                state=state,
            )

        reply = result.get("content") or ""
        tool_calls = result.get("tool_calls", [])

        logger.info(
            "llm.complete",
            extra={
                "tool_calls": [tc["name"] for tc in tool_calls],
                "has_content": bool(reply),
            },
        )

        # Execute tool calls sequentially — pure dispatch, zero business logic
        blocks: list[dict] = []

        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments", {})

            if name == "update_trip":
                state = self._apply_state_update(state, args)

            elif name == "search_flights":
                search_resp = await self._execute_agent(
                    "flight_search", state, trimmed,
                )
                if search_resp:
                    reply = self._append_content(reply, search_resp.content)
                    blocks.extend(search_resp.blocks)
                    state = search_resp.state or state

            elif name == "calculate_budget":
                budget_resp = await self._execute_agent(
                    "companion_budget", state, trimmed,
                )
                if budget_resp:
                    reply = self._append_content(reply, budget_resp.content)
                    blocks.extend(budget_resp.blocks)
                    state = budget_resp.state or state

            elif name == "ask_user":
                question = args.get("question", "")
                block_type = args.get("block_type", "text")
                if question and question not in reply:
                    reply = self._append_content(reply, question)
                if block_type == "companion_prompt":
                    blocks.append({
                        "type": "companion_prompt",
                        "data": {"question": question},
                    })
                    state.companions.asked = True
                elif block_type == "companion_dates_prompt":
                    blocks.append({
                        "type": "companion_dates_prompt",
                        "data": {"question": question},
                    })
                    state.companions.dates_asked = True

            elif name == "mark_complete":
                state.stage = "ready"
                state.trip_ready = True

        # Safety net: if LLM only called update_trip with no follow-up action,
        # generate the appropriate follow-up question
        only_update = (
            tool_calls
            and all(tc["name"] == "update_trip" for tc in tool_calls)
        )
        if only_update and state.legs and not state.trip_ready:
            cabin = state.legs[0].cabin_class.lower()
            has_airline = any(leg.preferred_airline for leg in state.legs)
            any_searched = any(leg.searched for leg in state.legs)
            all_have_dates = all(leg.preferred_date for leg in state.legs)

            if not all_have_dates:
                q = "When are you planning to travel?"
                reply = self._append_content(reply, q)
            elif cabin in ("business", "first") and not has_airline and not any_searched:
                q = ("Do you have a preferred airline or loyalty program "
                     "for this trip?")
                reply = self._append_content(reply, q)
            elif cabin in ("business", "first") and has_airline and not any_searched:
                # Has airline but LLM didn't trigger search — do it now
                search_resp = await self._execute_agent(
                    "flight_search", state, trimmed,
                )
                if search_resp:
                    reply = self._append_content(reply, search_resp.content)
                    blocks.extend(search_resp.blocks)
                    state = search_resp.state or state

        # Safety net: if companions > 0 but dates question not asked, ask it FIRST
        # (must come before budget calculation so we know travel dates)
        if (state.companions.count > 0
                and not state.companions.dates_asked
                and not any(b.get("type") == "companion_dates_prompt" for b in blocks)):
            q = "Will your companions be traveling on the same dates as you, or different dates?"
            reply = self._append_content(reply, q)
            blocks.append({
                "type": "companion_dates_prompt",
                "data": {"question": q},
            })
            state.companions.dates_asked = True

        # Safety net: if search ran + companions > 0 + dates resolved + budget not calculated,
        # auto-trigger budget (LLM may not call it due to sequencing)
        dates_resolved = state.companions.same_dates is not None
        if (any(leg.searched for leg in state.legs)
                and state.companions.count > 0
                and dates_resolved
                and not state.companions.budget_calculated
                and not any(tc["name"] == "calculate_budget" for tc in tool_calls)):
            budget_resp = await self._execute_agent(
                "companion_budget", state, trimmed,
            )
            if budget_resp:
                reply = self._append_content(reply, budget_resp.content)
                blocks.extend(budget_resp.blocks)
                state = budget_resp.state or state

        # Apply budget recommendation to legs — the recommendation IS the state
        if state.companions.budget_calculated and state.companions.recommended_cabin:
            total_pax = 1 + state.companions.count
            for leg in state.legs:
                leg.cabin_class = state.companions.recommended_cabin
                leg.passengers = total_pax

        # Safety net: if all conditions met but LLM didn't call mark_complete
        if not state.trip_ready and self._can_auto_complete(state):
            state.stage = "ready"
            state.trip_ready = True

        # Fallback: if LLM returned no text (only tool calls), generate a brief reply
        if not reply and state.trip_ready:
            reply = "Your trip is all set!"
        elif not reply and tool_calls:
            reply = "Got it, I've updated your trip details."

        response = AgentResponse(
            content=reply,
            blocks=blocks,
            state=state,
            trip_ready=state.trip_ready,
        )

        total_ms = (time.perf_counter() - request_start) * 1000
        logger.info(
            "coordinator.complete",
            extra={
                "total_duration_ms": round(total_ms),
                "stage": state.stage,
                "trip_ready": response.trip_ready,
                "tools_executed": [tc["name"] for tc in tool_calls],
            },
        )
        return response

    # ------------------------------------------------------------------
    # State update — merge LLM output into ConversationState
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_state_update(
        state: ConversationState, args: dict,
    ) -> ConversationState:
        """Merge LLM's update_trip arguments into state."""
        if "legs" in args:
            new_legs: list[LegState] = []
            for i, leg_data in enumerate(args["legs"]):
                pdate = leg_data.get("preferred_date")
                # Preserve search results from prior turns
                old_leg = state.legs[i] if i < len(state.legs) else None
                new_legs.append(LegState(
                    sequence=leg_data.get("sequence", i + 1),
                    origin_city=leg_data.get("origin_city", ""),
                    origin_airport=leg_data.get("origin_airport", ""),
                    destination_city=leg_data.get("destination_city", ""),
                    destination_airport=leg_data.get("destination_airport", ""),
                    preferred_date=(
                        date.fromisoformat(pdate) if pdate else None
                    ),
                    flexibility_days=leg_data.get("flexibility_days", 3),
                    cabin_class=leg_data.get("cabin_class", "economy"),
                    passengers=leg_data.get("passengers", 1),
                    preferred_airline=leg_data.get("preferred_airline", ""),
                    searched=old_leg.searched if old_leg else False,
                    anchor_flight=old_leg.anchor_flight if old_leg else None,
                    anchor_price=old_leg.anchor_price if old_leg else None,
                ))
            # Auto-add return leg: corporate travel is round-trip by default
            if len(new_legs) == 1 and new_legs[0].preferred_date:
                ob = new_legs[0]
                # Return Saturday after 5 working days (departure + 6 days)
                return_date = ob.preferred_date + timedelta(days=6)
                new_legs.append(LegState(
                    sequence=2,
                    origin_city=ob.destination_city,
                    origin_airport=ob.destination_airport,
                    destination_city=ob.origin_city,
                    destination_airport=ob.origin_airport,
                    preferred_date=return_date,
                    flexibility_days=ob.flexibility_days,
                    cabin_class=ob.cabin_class,
                    passengers=ob.passengers,
                    preferred_airline=ob.preferred_airline,
                ))

            state.legs = new_legs

        if "companions_count" in args:
            cc = args["companions_count"]
            if cc >= 0:
                state.companions.count = cc
                state.companions.asked = True

        if "companions_same_dates" in args:
            state.companions.same_dates = args["companions_same_dates"]
            state.companions.dates_asked = True

        if "confidence" in args:
            state.confidence = args["confidence"]
        if "interpretation_notes" in args:
            state.interpretation_notes = args["interpretation_notes"]

        return state

    # ------------------------------------------------------------------
    # Agent execution — precondition-guarded dispatch
    # ------------------------------------------------------------------

    async def _execute_agent(
        self,
        agent_type: str,
        state: ConversationState,
        history: list[dict],
    ) -> AgentResponse | None:
        """Run an agent with precondition check and timeout."""
        if agent_type == "flight_search":
            from app.services.agents.flight_search_agent import FlightSearchAgent
            agent = FlightSearchAgent()
        elif agent_type == "companion_budget":
            from app.services.agents.companion_budget_agent import CompanionBudgetAgent
            agent = CompanionBudgetAgent()
        else:
            logger.warning("Unknown agent type: %s", agent_type)
            return None

        agent_name = type(agent).__name__

        # Safety guard — not flow control
        err = agent.check_preconditions(state)
        if err:
            logger.warning("%s precondition failed: %s", agent_name, err)
            return None

        agent_start = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                agent.process("", state, history),
                timeout=_AGENT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("%s timed out after %.0fs", agent_name, _AGENT_TIMEOUT)
            return None
        except Exception as e:
            logger.error("%s failed: %s", agent_name, e, exc_info=True)
            return None

        agent_ms = (time.perf_counter() - agent_start) * 1000
        logger.info(
            "agent.complete",
            extra={
                "agent": agent_name,
                "duration_ms": round(agent_ms),
                "blocks_count": len(resp.blocks),
            },
        )
        return resp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _can_auto_complete(state: ConversationState) -> bool:
        """Check if all conditions for trip completion are met."""
        if not state.legs:
            return False
        all_have_data = all(
            leg.origin_airport and leg.destination_airport and leg.preferred_date
            for leg in state.legs
        )
        if not all_have_data:
            return False

        # Companions must be resolved for ALL cabin classes
        companions_resolved = (
            state.companions.count == 0  # Solo confirmed
            or state.companions.budget_calculated  # Budget done for companions
        )

        cabin = state.legs[0].cabin_class.lower()
        if cabin not in ("business", "first"):
            # Economy/premium: ready when legs complete + companions resolved
            return companions_resolved
        # Business/first: also need search completed
        all_searched = all(leg.searched for leg in state.legs)
        return all_searched and companions_resolved

    @staticmethod
    def _append_content(base: str, addition: str) -> str:
        """Append text with separator."""
        if not addition:
            return base
        if not base:
            return addition
        return base + "\n\n" + addition

    def _trim_history(
        self, history: list[dict], state: ConversationState,
    ) -> list[dict]:
        """Trim conversation history to bound token usage."""
        if len(history) <= _MAX_HISTORY_MSGS:
            return history
        summary = self._build_state_summary(state)
        return [
            {"role": "assistant", "content": f"[Previous context: {summary}]"},
        ] + history[-_MAX_HISTORY_MSGS:]

    @staticmethod
    def _build_state_summary(state: ConversationState) -> str:
        """Build a concise text summary from structured state."""
        parts = []
        if state.legs:
            leg_strs = []
            for leg in state.legs:
                s = f"{leg.origin_airport}\u2192{leg.destination_airport}"
                if leg.preferred_date:
                    s += f" {leg.preferred_date.strftime('%b %d')}"
                if leg.anchor_price:
                    s += f" anchor ${leg.anchor_price:,.0f}"
                if leg.preferred_airline:
                    s += f" pref:{leg.preferred_airline}"
                leg_strs.append(s)
            parts.append("Legs: " + ", ".join(leg_strs))
        if state.legs:
            parts.append(f"Cabin: {state.legs[0].cabin_class}")
        if state.companions.count > 0:
            parts.append(f"Companions: {state.companions.count}")
        parts.append(f"Stage: {state.stage}")
        return "; ".join(parts)
