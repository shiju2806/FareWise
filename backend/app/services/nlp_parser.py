"""NLP parser service — uses LLM (OpenAI primary, Anthropic fallback) to parse natural language trip descriptions."""

import json
import logging
from datetime import date, timedelta

from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a travel itinerary parser. Given a natural language trip description,
extract structured travel legs. Today's date is {today}. The current year is {year}.

CRITICAL: All dates MUST use the current year ({year}) or later. NEVER output a date in the past. If the user says "April 15", that means {year}-04-15.

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
    Example: "mid April" anchor = {year}-04-15 (Wed) → shift to Sunday {year}-04-12. "Early March" anchor = {year}-03-03 (Tue) → shift to Sunday {year}-03-01.
  - For round trips with no explicit return: default to 5 WORKING DAYS (Mon–Fri), returning Saturday.
    If departing Sunday → return the following Saturday (6 calendar nights). If departing Monday → return Saturday (5 calendar nights).
    Examples: depart Sun {year}-04-12 → return Sat {year}-04-18. Depart Mon {year}-03-02 → return Sat {year}-03-07.
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
        system = SYSTEM_PROMPT.format(today=date.today().isoformat(), year=date.today().year)

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


nlp_parser = NLPParser()
