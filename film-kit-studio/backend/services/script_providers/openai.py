"""
OpenAI Script LLM Provider.

Uses OpenAI Chat Completions API (gpt-4o, gpt-4-turbo, etc.).
"""

import os
from typing import Optional

from config import settings
from .base import ScriptLLMProvider


class OpenAIProvider:
    """OpenAI LLM provider."""

    name = "openai"

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("OpenAI API key not configured")

        # Lazy import - only needed if this provider is selected
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content or ""


openai_provider = OpenAIProvider()