"""
Google Gemini Script LLM Provider.

Uses Gemini generateContent API. Reuses the existing gemini_api_key from config.
"""

from config import settings
from .base import ScriptLLMProvider


class GeminiProvider:
    """Google Gemini LLM provider."""

    name = "gemini"

    def __init__(self) -> None:
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("Gemini API key not configured")

        # Lazy import
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        # Convert messages to Gemini format
        contents = []
        system_instruction = None
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            else:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or 8192,
            system_instruction=system_instruction,
        )

        response = await client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        return response.text or ""


gemini_provider = GeminiProvider()