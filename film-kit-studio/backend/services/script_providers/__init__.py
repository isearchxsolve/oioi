"""
Pluggable Script LLM Provider Registry.

Providers implement a simple async protocol: chat(messages, temperature, max_tokens) -> str
Registry picks the provider based on config.script_provider (nim|openai|anthropic|gemini).
"""

from .base import ScriptLLMProvider
from .registry import get_script_provider, generate_script

__all__ = ["ScriptLLMProvider", "get_script_provider", "generate_script"]