"""Unified LLM client — tries OpenAI first, falls back to Anthropic."""

import logging

from openai import AsyncOpenAI
import anthropic

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified async LLM client with OpenAI primary + Anthropic fallback."""

    def __init__(self):
        self._openai = None
        self._anthropic = None

        if settings.openai_api_key:
            self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        if settings.anthropic_api_key:
            self._anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(
        self,
        system: str,
        user: str,
        *,
        messages: list[dict] | None = None,
        max_tokens: int = 1000,
        temperature: float = 0,
        json_mode: bool = False,
    ) -> str:
        """Get a completion from the best available LLM.

        Args:
            system: System prompt
            user: User message (ignored if messages is provided)
            messages: Full message list (for multi-turn). Should NOT include system.
            max_tokens: Max output tokens
            temperature: Sampling temperature
            json_mode: If True, force JSON output (OpenAI response_format)

        Returns:
            Raw text response from the LLM.

        Raises:
            RuntimeError if both providers fail.
        """
        errors = []

        # Build message list
        if messages:
            chat_messages = list(messages)
        else:
            chat_messages = [{"role": "user", "content": user}]

        # Try OpenAI first
        if self._openai:
            try:
                openai_messages = [{"role": "system", "content": system}] + chat_messages
                kwargs: dict = {
                    "model": "gpt-4o-mini",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": openai_messages,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = await self._openai.chat.completions.create(**kwargs)
                return response.choices[0].message.content.strip()
            except Exception as e:
                errors.append(f"OpenAI: {e}")
                logger.warning(f"OpenAI failed, trying Anthropic: {e}")

        # Fallback to Anthropic
        if self._anthropic:
            try:
                response = await self._anthropic.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=chat_messages,
                )
                return response.content[0].text.strip()
            except Exception as e:
                errors.append(f"Anthropic: {e}")
                logger.warning(f"Anthropic also failed: {e}")

        raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")


# Singleton
llm_client = LLMClient()
