"""NLP parser service — uses LLM (OpenAI primary, Anthropic fallback) to parse natural language trip descriptions."""

import json
import logging
from datetime import date, timedelta

from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a travel itinerary parser. Given a natural language trip description,
extract structured travel legs. Today's date is {today}.

Rules:
- Resolve relative dates ("next Tuesday", "this Friday") against today's date
- For vague date expressions, use the anchor date and WIDEN flexibility so the search covers a good range:
  - "Mid [month]" -> preferred_date = the 15th, flexibility_days = 5 (search will cover 10th-20th)
  - "Early [month]" -> preferred_date = the 3rd, flexibility_days = 4 (covers 1st-7th)
  - "End of [month]" / "Late [month]" -> preferred_date = the 25th, flexibility_days = 4
  - "Next week" -> preferred_date = Monday of next week, flexibility_days = 3
  - When the user gives a SPECIFIC date ("April 15"), use flexibility_days = 3 (default)
- This is a CORPORATE travel tool — all trips are business trips regardless of cabin class.
- CORPORATE DATE LOGIC (applies to ALL cabin classes):
  - When dates are vague ("mid April", "early March"), shift the preferred_date to the nearest Sunday ON or BEFORE the anchor date, so the traveler arrives Monday for start of the business week.
    Example: "mid April" anchor = Apr 15 (Wed) → shift to Sunday Apr 12. "Early March" anchor = Mar 3 (Tue) → shift to Sunday Mar 1.
  - For round trips with no explicit return: default to 5 WORKING DAYS (Mon–Fri), returning Saturday.
    If departing Sunday → return the following Saturday (6 calendar nights). If departing Monday → return Saturday (5 calendar nights).
    Examples: depart Sun Apr 12 → return Sat Apr 18. Depart Mon Mar 2 → return Sat Mar 7.
    A typical corporate round trip covers one working week. NEVER suggest a trip longer than 7 days unless the user explicitly asks.
  - When the user gives a SPECIFIC date ("April 15"), respect it as-is (don't shift to Sunday).
- Infer return legs if the trip implies returning home (e.g., "Toronto to NYC and back")
- For multi-city trips, infer connecting legs
- Default cabin class: economy
- Default flexibility: 3 days (increase for vague dates as described above)
- Default passengers: 1
- Map city names to primary IATA airport codes using common knowledge
- If a city has multiple airports, use the primary one but note alternatives
- If any part is ambiguous, include it in interpretation_notes
- In interpretation_notes, explain your date choice: "Mid April -> shifted to Sun Apr 12 (arrive Mon), return Sat Apr 18 (5 working days), ±5 day flexibility"

Edge cases:
- MULTI-AIRPORT CITIES: Use the primary airport, note alternatives in interpretation_notes.
  Toronto → YYZ (note: YTZ Billy Bishop for short-haul). London → LHR (note: LGW, STN, LCY).
  New York → JFK for international, EWR for domestic. Paris → CDG (note: ORY).
  Washington → DCA for domestic, IAD for international. Chicago → ORD (note: MDW).
- "leave Monday, return Friday" = 4 calendar nights (Mon depart, Fri return). Count the days literally.
- "meeting on [date]" → set preferred_date to the day BEFORE (arrive evening before), return the day AFTER the meeting.
- "day trip" or "same day return" → create outbound and return legs on the same date.
- Multi-city (e.g., "Toronto to NYC then Boston then home") → create legs 1→2, 2→3, 3→1.
- If city is ambiguous (e.g., "Portland" could be PDX or PWM), use the more common one (PDX) and note the ambiguity in interpretation_notes.

Respond ONLY with valid JSON, no markdown, no preamble:
{{
    "confidence": 0.0-1.0,
    "legs": [
        {{
            "sequence": 1,
            "origin_city": "City Name",
            "origin_airport": "IATA",
            "destination_city": "City Name",
            "destination_airport": "IATA",
            "preferred_date": "YYYY-MM-DD",
            "flexibility_days": 3,
            "cabin_class": "economy",
            "passengers": 1
        }}
    ],
    "interpretation_notes": "Any assumptions or clarifications"
}}"""


class NLPParser:
    """Parses natural language trip descriptions into structured trip data."""

    async def parse(self, text: str, max_retries: int = 2) -> dict:
        """
        Parse a natural language trip description.

        Returns dict with keys: confidence, legs, interpretation_notes.
        On failure, returns a low-confidence result so the frontend can show
        the structured form for manual entry.
        """
        system = SYSTEM_PROMPT.format(today=date.today().isoformat())

        raw = ""
        for attempt in range(max_retries + 1):
            try:
                raw = await llm_client.complete(system=system, user=text, max_tokens=1000, temperature=0, json_mode=True)
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    raw = "\n".join(lines).strip()
                parsed = json.loads(raw)

                # Validate structure
                if "legs" not in parsed or not isinstance(parsed["legs"], list):
                    raise ValueError("Missing or invalid 'legs' field")

                if "confidence" not in parsed:
                    parsed["confidence"] = 0.8

                self._snap_dates(parsed)
                return parsed

            except json.JSONDecodeError as e:
                logger.warning(f"NLP parse attempt {attempt + 1}: invalid JSON response: {e}\nRaw: {raw[:500]}")
                if attempt == max_retries:
                    return self._fallback_response(text)
            except Exception as e:
                logger.error(f"NLP parse attempt {attempt + 1}: OpenAI API error: {e}")
                if attempt == max_retries:
                    return self._fallback_response(text)

        return self._fallback_response(text)

    @staticmethod
    def _snap_dates(parsed: dict) -> None:
        """Post-process: validate parsed date strings."""
        for leg in parsed.get("legs", []):
            raw_date = leg.get("preferred_date")
            if not raw_date:
                continue
            try:
                d = date.fromisoformat(raw_date)
                leg["preferred_date"] = d.isoformat()
            except (ValueError, TypeError):
                pass

    def _fallback_response(self, original_text: str) -> dict:
        """Return a low-confidence result when parsing fails."""
        return {
            "confidence": 0.0,
            "legs": [],
            "interpretation_notes": (
                "Could not parse the trip description automatically. "
                "Please use the structured form to enter your trip details."
            ),
            "original_text": original_text,
        }


CHAT_SYSTEM_PROMPT = """You are a friendly, decisive travel planning assistant for a corporate travel tool. Today is {today}.

Help users plan trips through brief conversation. Given the conversation history and any partial trip data, do TWO things:
1. Generate a brief, friendly reply (1-2 sentences max)
2. Update the structured trip data with any new information

IMPORTANT — be decisive, not interrogative:
- When the user gives enough info to act (origin, destination, rough timeframe), FILL IN sensible defaults and set trip_ready=true. Do NOT keep asking questions.
- This is a CORPORATE travel tool — all trips are business trips regardless of cabin class.
- Vague date anchors:
  - "Mid [month]" → anchor = the 15th, flexibility_days = 5.
  - "Early [month]" → anchor = the 3rd, flexibility_days = 4.
  - "End of month" / "Late [month]" → anchor = the 25th, flexibility_days = 4.
  - "Next week" → anchor = Monday of next week, flexibility_days = 3.
  - When the user gives a SPECIFIC date ("March 20"), use that date as-is (don't shift), flexibility_days = 3.
- "Business" → set cabin_class to business. If no class mentioned, default to economy.
- CORPORATE DATE LOGIC (applies to ALL cabin classes since this is a corporate tool):
  - When dates are vague ("mid April", "early March"), shift the preferred_date to the nearest Sunday ON or BEFORE the anchor date, so the traveler arrives Monday for start of the business week.
    Example: "mid April" anchor = Apr 15 (Wed) → shift to Sunday Apr 12. "Early March" anchor = Mar 3 (Tue) → shift to Sunday Mar 1.
  - For round trips with no explicit return: default to 5 WORKING DAYS (Mon–Fri), returning Saturday.
    If departing Sunday → return the following Saturday (6 calendar nights). If departing Monday → return Saturday (5 calendar nights).
    Examples: depart Sun Apr 12 → return Sat Apr 18. Depart Mon Mar 2 → return Sat Mar 7.
    A typical corporate round trip covers one working week. NEVER exceed 7 days unless the user explicitly asks.
  - In your reply, note this logic: "I've set departure to Sunday Apr 12 so you arrive Monday, with return Saturday Apr 18 after a full work week."
- "Round trip" or "and back" → add a return leg matching the requested duration. If user says "for a week" → 7 days. NEVER exceed the requested duration.
- In your reply, when dates are vague, briefly note the flexibility: e.g., "I've set departure around mid-April with a ±5 day window to find the best fares."
- When the user says "book", "let's go", "search", or "find flights" — proceed immediately with what you have. Use defaults for anything missing.
- Only ask a question if you truly cannot infer the origin OR destination.

Edge cases:
- "meeting on [date]" → set preferred_date to the day BEFORE (arrive evening before), return the day AFTER the meeting. Mention this in your reply: "I've set arrival for the evening before your meeting."
- "day trip" or "same day return" → create two legs on the same date. Note: flexibility_days = 0 for day trips.
- Multi-city (e.g., "Toronto to NYC then Boston then home") → create legs 1→2, 2→3, 3→1. Set appropriate dates with 2-3 days per city.
- MULTI-AIRPORT CITIES: Use the primary airport. Toronto → YYZ, London → LHR, New York → JFK (international) or EWR (domestic), Paris → CDG, Washington → DCA (domestic) or IAD (international).
- Ambiguous cities (e.g., "Portland") → use the more common one (PDX) and ask: "I'm assuming Portland, Oregon (PDX) — did you mean Portland, Maine?"

Required fields before a trip is ready:
- At least one leg with: origin_city, destination_city, preferred_date
- If user implies round trip, add a return leg

Respond ONLY with valid JSON, no markdown:
{{
    "reply": "Your brief message to the user",
    "partial_trip": {{
        "confidence": 0.0-1.0,
        "legs": [
            {{
                "sequence": 1,
                "origin_city": "City Name",
                "origin_airport": "IATA",
                "destination_city": "City Name",
                "destination_airport": "IATA",
                "preferred_date": "YYYY-MM-DD",
                "flexibility_days": 3,
                "cabin_class": "economy",
                "passengers": 1
            }}
        ],
        "interpretation_notes": ""
    }},
    "trip_ready": false,
    "missing_fields": ["return_date", "cabin_class"]
}}"""


class NLPChatParser:
    """Multi-turn conversational trip planning parser."""

    async def chat(
        self,
        message: str,
        conversation_history: list[dict] | None = None,
        partial_trip: dict | None = None,
    ) -> dict:
        """
        Process a chat message in the trip planning conversation.

        Returns dict with: reply, partial_trip, trip_ready, missing_fields.
        """
        system = CHAT_SYSTEM_PROMPT.format(today=date.today().isoformat())

        if partial_trip:
            system += f"\n\nCurrent partial trip data:\n{json.dumps(partial_trip, indent=2)}"

        msgs = list(conversation_history or [])
        msgs.append({"role": "user", "content": message})

        try:
            raw = await llm_client.complete(system=system, user="", messages=msgs, max_tokens=1000, temperature=0, json_mode=True)
            if raw.startswith("```"):
                lines = raw.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw = "\n".join(lines).strip()

            parsed = json.loads(raw)

            # Validate required fields
            if "reply" not in parsed:
                parsed["reply"] = "I can help you plan that trip. What are the details?"
            if "partial_trip" not in parsed:
                parsed["partial_trip"] = partial_trip
            if "trip_ready" not in parsed:
                parsed["trip_ready"] = False
            if "missing_fields" not in parsed:
                parsed["missing_fields"] = []

            # Snap dates
            pt = parsed.get("partial_trip")
            if pt and isinstance(pt, dict):
                for leg in pt.get("legs", []):
                    raw_date = leg.get("preferred_date")
                    if raw_date:
                        try:
                            d = date.fromisoformat(raw_date)
                            leg["preferred_date"] = d.isoformat()
                        except (ValueError, TypeError):
                            pass

            return parsed

        except json.JSONDecodeError as e:
            logger.warning(f"Chat parse error: {e}")
            return {
                "reply": "I understand. Could you tell me where you'd like to travel, when, and from where?",
                "partial_trip": partial_trip,
                "trip_ready": False,
                "missing_fields": ["origin", "destination", "date"],
            }
        except Exception as e:
            logger.error(f"Chat parse unexpected error: {e}", exc_info=True)
            return {
                "reply": "I understand. Could you tell me where you'd like to travel, when, and from where?",
                "partial_trip": partial_trip,
                "trip_ready": False,
                "missing_fields": ["origin", "destination", "date"],
            }


nlp_parser = NLPParser()
nlp_chat_parser = NLPChatParser()
