"""NLP parser service — uses Claude API to parse natural language trip descriptions."""

import json
import logging
from datetime import date

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a travel itinerary parser. Given a natural language trip description,
extract structured travel legs. Today's date is {today}.

Rules:
- Resolve relative dates ("next Tuesday", "this Friday") against today's date
- Infer return legs if the trip implies returning home (e.g., "Toronto to NYC and back")
- For multi-city trips, infer connecting legs
- Default cabin class: economy
- Default flexibility: 3 days
- Default passengers: 1
- Map city names to primary IATA airport codes using common knowledge
- If a city has multiple airports, use the primary one but note alternatives
- If any part is ambiguous, include it in interpretation_notes

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

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def parse(self, text: str, max_retries: int = 2) -> dict:
        """
        Parse a natural language trip description.

        Returns dict with keys: confidence, legs, interpretation_notes.
        On failure, returns a low-confidence result so the frontend can show
        the structured form for manual entry.
        """
        system = SYSTEM_PROMPT.format(today=date.today().isoformat())

        for attempt in range(max_retries + 1):
            try:
                message = await self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=1000,
                    temperature=0,
                    system=system,
                    messages=[{"role": "user", "content": text}],
                )

                raw = message.content[0].text.strip()
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    # Remove first line (```json) and last line (```)
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    raw = "\n".join(lines).strip()
                parsed = json.loads(raw)

                # Validate structure
                if "legs" not in parsed or not isinstance(parsed["legs"], list):
                    raise ValueError("Missing or invalid 'legs' field")

                if "confidence" not in parsed:
                    parsed["confidence"] = 0.8

                return parsed

            except json.JSONDecodeError as e:
                logger.warning(f"NLP parse attempt {attempt + 1}: invalid JSON response: {e}\nRaw: {raw[:500]}")
                if attempt == max_retries:
                    return self._fallback_response(text)
            except anthropic.APIError as e:
                logger.error(f"NLP parse attempt {attempt + 1}: Anthropic API error: {e}")
                if attempt == max_retries:
                    return self._fallback_response(text)
            except Exception as e:
                logger.error(f"NLP parse attempt {attempt + 1}: unexpected error: {e}")
                if attempt == max_retries:
                    return self._fallback_response(text)

        return self._fallback_response(text)

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
- "Mid March" → pick the 15th. "Next week" → pick the Monday. "End of month" → pick the 28th.
- "Round trip" or "and back" → add a return leg 5-7 days later by default.
- "Business" → set cabin_class to business. If no class mentioned, default to economy.
- When the user says "book", "let's go", "search", or "find flights" — proceed immediately with what you have. Use defaults for anything missing.
- Only ask a question if you truly cannot infer the origin OR destination.

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

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

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

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": message})

        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                temperature=0,
                system=system,
                messages=messages,
            )

            raw = response.content[0].text.strip()
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

            return parsed

        except (json.JSONDecodeError, anthropic.APIError, Exception) as e:
            logger.error(f"Chat parse error: {e}")
            return {
                "reply": "I understand. Could you tell me where you'd like to travel, when, and from where?",
                "partial_trip": partial_trip,
                "trip_ready": False,
                "missing_fields": ["origin", "destination", "date"],
            }


nlp_parser = NLPParser()
nlp_chat_parser = NLPChatParser()
