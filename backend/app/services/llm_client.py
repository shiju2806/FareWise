"""Unified LLM client — tries OpenAI first, falls back to Anthropic."""

import asyncio
import json
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
        model: str | None = None,
    ) -> str:
        """Get a completion from the best available LLM.

        Args:
            system: System prompt
            user: User message (ignored if messages is provided)
            messages: Full message list (for multi-turn). Should NOT include system.
            max_tokens: Max output tokens
            temperature: Sampling temperature
            json_mode: If True, force JSON output (OpenAI response_format)
            model: Specific model to use (e.g. "gpt-4o", "claude-sonnet-4-5-20250929").
                   Routes to the correct provider based on model name prefix.
                   If None, uses default fallback chain (OpenAI → Anthropic).

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

        # Route to specific provider if model is specified
        if model:
            is_openai_model = model.startswith(("gpt-", "o1-", "o3-", "o4-"))
            is_anthropic_model = model.startswith("claude-")

            if is_openai_model and self._openai:
                try:
                    return await self._call_openai(
                        model, system, chat_messages, max_tokens, temperature, json_mode
                    )
                except Exception as e:
                    errors.append(f"OpenAI ({model}): {e}")
                    logger.warning(f"OpenAI {model} failed: {e}")

            elif is_anthropic_model and self._anthropic:
                try:
                    return await self._call_anthropic(
                        model, system, chat_messages, max_tokens, temperature
                    )
                except Exception as e:
                    errors.append(f"Anthropic ({model}): {e}")
                    logger.warning(f"Anthropic {model} failed: {e}")

        # Default fallback chain: OpenAI → Anthropic
        if self._openai and not any("OpenAI" in e for e in errors):
            try:
                return await self._call_openai(
                    "gpt-4o-mini", system, chat_messages, max_tokens, temperature, json_mode
                )
            except Exception as e:
                errors.append(f"OpenAI: {e}")
                logger.warning(f"OpenAI failed, trying Anthropic: {e}")

        if self._anthropic and not any("Anthropic" in e for e in errors):
            try:
                return await self._call_anthropic(
                    "claude-sonnet-4-5-20250929", system, chat_messages,
                    max_tokens, temperature,
                )
            except Exception as e:
                errors.append(f"Anthropic: {e}")
                logger.warning(f"Anthropic also failed: {e}")

        raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")

    _LLM_TIMEOUT = 15.0  # seconds per LLM call

    async def _call_openai(
        self, model: str, system: str, chat_messages: list[dict],
        max_tokens: int, temperature: float, json_mode: bool,
    ) -> str:
        openai_messages = [{"role": "system", "content": system}] + chat_messages
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": openai_messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await asyncio.wait_for(
            self._openai.chat.completions.create(**kwargs),
            timeout=self._LLM_TIMEOUT,
        )
        return response.choices[0].message.content.strip()

    async def _call_anthropic(
        self, model: str, system: str, chat_messages: list[dict],
        max_tokens: int, temperature: float,
    ) -> str:
        response = await asyncio.wait_for(
            self._anthropic.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=chat_messages,
            ),
            timeout=self._LLM_TIMEOUT,
        )
        return response.content[0].text.strip()

    # ------------------------------------------------------------------
    # Tool-calling completions
    # ------------------------------------------------------------------

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        *,
        messages: list[dict] | None = None,
        tools: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0,
        model: str | None = None,
        tool_choice: str | None = None,
    ) -> dict:
        """Get a completion with tool-calling support.

        Args:
            system: System prompt.
            user: User message (ignored if *messages* is provided).
            messages: Full message list (multi-turn). Should NOT include system.
            tools: Tool definitions in OpenAI-compatible format::

                [{"name": "...", "description": "...", "parameters": {JSON Schema}}]

            max_tokens: Max output tokens.
            temperature: Sampling temperature.
            model: Specific model to use; routes by prefix. Default fallback chain.
            tool_choice: "auto" (default), "required" (must call >=1 tool), or "none".

        Returns:
            dict with keys:
                content   – str | None  (text portion of the response)
                tool_calls – list[dict]  ([{id, name, arguments}])
                stop_reason – str        ("end_turn" | "tool_use")
        """
        errors: list[str] = []

        chat_messages = list(messages) if messages else [{"role": "user", "content": user}]

        # Route to specific provider
        if model:
            if model.startswith(("gpt-", "o1-", "o3-", "o4-")) and self._openai:
                try:
                    return await self._call_openai_tools(
                        model, system, chat_messages, tools, max_tokens, temperature,
                        tool_choice=tool_choice,
                    )
                except Exception as e:
                    errors.append(f"OpenAI ({model}): {e}")
                    logger.warning("OpenAI %s tools failed: %s", model, e)

            elif model.startswith("claude-") and self._anthropic:
                try:
                    return await self._call_anthropic_tools(
                        model, system, chat_messages, tools, max_tokens, temperature,
                        tool_choice=tool_choice,
                    )
                except Exception as e:
                    errors.append(f"Anthropic ({model}): {e}")
                    logger.warning("Anthropic %s tools failed: %s", model, e)

        # Default fallback chain
        if self._openai and not any("OpenAI" in e for e in errors):
            try:
                return await self._call_openai_tools(
                    "gpt-4o-mini", system, chat_messages, tools, max_tokens, temperature,
                    tool_choice=tool_choice,
                )
            except Exception as e:
                errors.append(f"OpenAI: {e}")
                logger.warning("OpenAI tools failed, trying Anthropic: %s", e)

        if self._anthropic and not any("Anthropic" in e for e in errors):
            try:
                return await self._call_anthropic_tools(
                    "claude-sonnet-4-5-20250929", system, chat_messages, tools,
                    max_tokens, temperature, tool_choice=tool_choice,
                )
            except Exception as e:
                errors.append(f"Anthropic: {e}")
                logger.warning("Anthropic tools also failed: %s", e)

        raise RuntimeError(f"All LLM providers failed (tools): {'; '.join(errors)}")

    async def _call_openai_tools(
        self, model: str, system: str, chat_messages: list[dict],
        tools: list[dict], max_tokens: int, temperature: float,
        *, tool_choice: str | None = None,
    ) -> dict:
        openai_messages = [{"role": "system", "content": system}] + chat_messages

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": openai_messages,
            "tools": openai_tools,
        }
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        response = await asyncio.wait_for(
            self._openai.chat.completions.create(**kwargs),
            timeout=self._LLM_TIMEOUT,
        )

        msg = response.choices[0].message
        content = msg.content.strip() if msg.content else None
        tool_calls = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })

        stop = "tool_use" if tool_calls else "end_turn"
        return {"content": content, "tool_calls": tool_calls, "stop_reason": stop}

    async def _call_anthropic_tools(
        self, model: str, system: str, chat_messages: list[dict],
        tools: list[dict], max_tokens: int, temperature: float,
        *, tool_choice: str | None = None,
    ) -> dict:
        anthropic_tools = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": chat_messages,
            "tools": anthropic_tools,
        }
        if tool_choice:
            # Anthropic format: {"type": "any"} for required
            tc_map = {"required": {"type": "any"}, "auto": {"type": "auto"}, "none": {"type": "none"}}
            kwargs["tool_choice"] = tc_map.get(tool_choice, {"type": "auto"})

        response = await asyncio.wait_for(
            self._anthropic.messages.create(**kwargs),
            timeout=self._LLM_TIMEOUT,
        )

        content = None
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content = block.text.strip()
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        stop = "tool_use" if tool_calls else "end_turn"
        return {"content": content, "tool_calls": tool_calls, "stop_reason": stop}


# Singleton
llm_client = LLMClient()
