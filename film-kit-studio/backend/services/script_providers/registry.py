"""
Script LLM Provider Registry.

Selects the active script provider based on config.script_provider.
Falls back to NIM if the selected provider isn't configured.
Exports a single `generate_script` facade with the same signature as the
old `nim_llm.generate_script` for drop-in replacement in pipeline.py.
"""

from typing import Optional

from config import settings, SCRIPT_SYSTEM_PROMPT
from utils.json_extract import extract_json_array
from utils.token_bucket import get_token_bucket

from .nim import nim_provider
from .openai import openai_provider
from .anthropic import anthropic_provider
from .gemini import gemini_provider


# Provider map
_PROVIDERS = {
    "nim": nim_provider,
    "openai": openai_provider,
    "anthropic": anthropic_provider,
    "gemini": gemini_provider,
}


def get_script_provider() -> object:
    """Return the active script LLM provider based on settings.script_provider."""
    provider_name = settings.script_provider.lower()
    provider = _PROVIDERS.get(provider_name)

    if provider is None:
        # Unknown provider -> fall back to NIM
        provider = nim_provider

    # If selected provider isn't configured, fall back to NIM (free default)
    if not provider.is_configured():
        provider = nim_provider

    return provider


async def generate_script(
    idea: str,
    style: str,
    num_scenes: int,
    aspect: str,
    system_prompt: str = SCRIPT_SYSTEM_PROMPT,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> list[dict]:
    """
    Generate a structured storyboard from a story idea.

    This is the drop-in replacement for nim_llm.generate_script().
    Same signature, same return type (list of scene dicts with cinematography fields).
    """
    provider = get_script_provider()

    # Build the user prompt
    user_prompt = f"""\
Story Idea: {idea}
Visual Style: {style}
Aspect Ratio: {aspect}
Number of Scenes: {num_scenes}

Generate exactly {num_scenes} scenes as a JSON array.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Rate limiting via token bucket (shared with NIM for RPM)
    bucket = get_token_bucket("nim_llm")
    await bucket.take()

    # Call the provider
    response_text = await provider.chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Extract and validate JSON array
    scenes = extract_json_array(response_text)

    # Validate each scene has required fields
    required = ["shot_type", "lens", "lighting", "camera_move", "color_grade", "narration", "visual_prompt"]
    for i, scene in enumerate(scenes):
        for field in required:
            if field not in scene:
                scene[field] = ""  # default empty rather than fail

    return scenes


# Export for convenience
__all__ = ["get_script_provider", "generate_script"]