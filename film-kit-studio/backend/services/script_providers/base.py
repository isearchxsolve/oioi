"""
Base protocol for Script LLM Providers.

All script providers implement this protocol. The interface is intentionally
simple: a single async chat() method that takes standard chat-completion
parameters and returns the model's text response.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ScriptLLMProvider(Protocol):
    """Protocol for script-generation LLM providers."""

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g., 'nim', 'openai', 'anthropic', 'gemini')."""
        ...

    def is_configured(self) -> bool:
        """Return True iff the provider has all required credentials configured."""
        ...

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."} dicts
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Optional max tokens in response

        Returns:
            The model's text response (may contain JSON array for scripts)
        """
        ...