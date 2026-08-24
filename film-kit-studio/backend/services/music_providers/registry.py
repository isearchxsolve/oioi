"""
Music provider registry.

Selects the active score backend from settings.music_provider, falling
back to the free FFMPEG synthesised bed when the requested provider
isn't configured (missing API key).

Exposes generate_score() — the uniform music-generation entry point used
by the pipeline's stitch step.
"""

import logging
from pathlib import Path

from config import settings
from services.music_providers.ffmpeg import FfmpegMusicProvider
from services.music_providers.suno import SunoMusicProvider

logger = logging.getLogger(__name__)


def get_music_provider():
    """Resolve the active music provider with fallback to the free bed."""
    name = (settings.music_provider or "ffmpeg").lower()

    if name == "suno":
        suno = SunoMusicProvider()
        if suno.is_configured():
            return suno
        logger.warning("MUSIC_PROVIDER=suno but SUNO_API_KEY unset — falling back to ffmpeg bed.")

    return FfmpegMusicProvider()


_provider = None


def _resolve():
    global _provider
    if _provider is None:
        _provider = get_music_provider()
        logger.info(f"Active music provider: {_provider.name}")
    return _provider


async def generate_score(duration: float, out_path: Path, mood: str = "ambient") -> Path:
    """Generate a background score via the active provider."""
    provider = _resolve()
    return await provider.generate(duration, out_path, mood)
