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


nlp_parser = NLPParser()
