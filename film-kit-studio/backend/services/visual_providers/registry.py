"""
Visual provider registry.

Selects the active visual backend from settings.visual_provider, with an
automatic fallback to the free Cosmos provider when the requested provider
isn't configured (missing API key). This guarantees the pipeline always
works out of the box with zero keys, while letting users opt into the
higher-quality cinematic tiers (Veo / Kling) by setting the relevant key.

Exposes generate_visual() with the exact signature the original
services/nim_cosmos.py used, so services/pipeline.py needs no changes
beyond a single import swap.
"""

import logging
from pathlib import Path
from typing import Optional

from config import settings
from services.visual_providers.base import ProgressCallback
from services.visual_providers.cosmos import CosmosVisualProvider
from services.visual_providers.kling import KlingVisualProvider
from services.visual_providers.veo import VeoVisualProvider

logger = logging.getLogger(__name__)


def get_visual_provider():
    """
    Resolve the active visual provider.

    Selection order:
      1. The provider named by settings.visual_provider, IF it is configured.
      2. Otherwise, fall back to Cosmos (the free default).
    """
    name = (settings.visual_provider or "cosmos").lower()

    if name == "veo":
        veo = VeoVisualProvider()
        if veo.is_configured():
            return veo
        logger.warning("VISUAL_PROVIDER=veo but GEMINI_API_KEY unset — falling back to cosmos.")
    elif name == "kling":
        kling = KlingVisualProvider()
        if kling.is_configured():
            return kling
        logger.warning("VISUAL_PROVIDER=kling but Kling credentials unset — falling back to cosmos.")

    return CosmosVisualProvider()


# Module-level singleton so the same provider instance + token bucket is reused.
_provider = None


def _resolve():
    global _provider
    if _provider is None:
        _provider = get_visual_provider()
        logger.info(f"Active visual provider: {_provider.name}")
    return _provider


async def generate_visual(
    visual_prompt: str,
    out_path: Path,
    aspect: str = "16:9",
    seed: Optional[int] = None,
    duration_seconds: float = 4.0,
    max_retries: int = 3,
    progress_callback: ProgressCallback = None,
) -> str:
    """Generate a scene visual via the active provider.

    Signature is identical to the legacy nim_cosmos.generate_visual so the
    pipeline orchestration code is unchanged.
    """
    provider = _resolve()
    return await provider.generate(
        visual_prompt=visual_prompt,
        out_path=out_path,
        aspect=aspect,
        seed=seed,
        duration_seconds=duration_seconds,
        max_retries=max_retries,
        progress_callback=progress_callback,
    )
