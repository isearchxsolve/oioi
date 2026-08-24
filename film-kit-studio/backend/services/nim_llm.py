"""
NVIDIA NIM LLM service — script & storyboard generation.

THIN WRAPPER: Now delegates to the pluggable script_providers registry.
The actual provider logic lives in services/script_providers/{nim,openai,anthropic,gemini}.py
This file retains the original generate_script() signature for backward compatibility
with pipeline.py (one import swap).
"""

import logging

from config import SCRIPT_SYSTEM_PROMPT, settings
from utils.json_extract import extract_json_array
from services.script_providers.registry import generate_script as _generate_script

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    pass


async def generate_script(
    idea: str,
    num_scenes: int,
    style: str,
) -> list[dict[str, str]]:
    """
    Generate a storyboard script from a story idea.

    Drop-in replacement for the original implementation.
    Now routes through the pluggable script provider registry.
    """
    user_prompt = (
        f"Story idea: {idea}\n"
        f"Visual style to weave into every visual_prompt: {style}\n"
        f"Produce exactly {num_scenes} scenes."
    )

    scenes = await _generate_script(
        idea=idea,
        style=style,
        num_scenes=num_scenes,
        aspect=settings.aspect if hasattr(settings, 'aspect') else "16:9",
        system_prompt=SCRIPT_SYSTEM_PROMPT,
        temperature=0.85,
        max_tokens=2000,
    )

    # Validate and format output to match original return type
    validated: list[dict[str, str]] = []
    for i, item in enumerate(scenes):
        if not isinstance(item, dict):
            logger.warning(f"Scene {i}: unexpected item type {type(item).__name__}, skipping")
            continue
        narration = str(item.get("narration", "")).strip()
        visual_prompt = str(item.get("visual_prompt", "")).strip()
        if not narration or not visual_prompt:
            logger.warning(f"Scene {i}: missing narration or visual_prompt, skipping")
            continue

        def _opt(key: str) -> str | None:
            v = item.get(key)
            s = str(v).strip() if v is not None else ""
            return s or None

        validated.append({
            "narration": narration,
            "visual_prompt": f"{visual_prompt}, {style}",
            "shot_type": _opt("shot_type"),
            "lens": _opt("lens"),
            "lighting": _opt("lighting"),
            "camera_move": _opt("camera_move"),
            "color_grade": _opt("color_grade"),
        })

    if not validated:
        raise LLMError("Model returned no usable scenes.")

    logger.info(f"Generated {len(validated)} scenes from idea: {idea[:80]}...")
    return validated
