"""
Anthropic Claude Script LLM Provider.

Uses Anthropic Messages API (Claude Sonnet 4, Opus, etc.).
Note: Anthropic uses a top-level 'system' parameter, not a system message.
"""

from config import settings
from .base import ScriptLLMProvider


class AnthropicProvider:
    """Anthropic LLM provider."""

    name = "anthropic"

    def __init__(self) -> None:
        self.api_key = settings.anthropic_api_key
        self.model = settings.anthropic_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("Anthropic API key not configured")

        # Lazy import
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.api_key)

        # Extract system prompt if present (Anthropic uses top-level 'system' param)
        system_prompt = None
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                filtered_messages.append(msg)

        kwargs = {
            "model": self.model,
            "messages": filtered_messages,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = await client.messages.create(**kwargs)

        # Anthropic returns a list of content blocks; concatenate text
        return "".join(block.text for block in response.content if hasattr(block, "text"))


anthropic_provider = AnthropicProvider()