"""
Voice provider registry.

Selects the active TTS backend from settings.voice_provider, falling back
to the free edge-tts provider when the requested provider isn't configured
(missing API key). Guarantees zero-key operation out of the box.

Exposes synthesize_narration() with the exact signature the original
services/tts.py used, so services/pipeline.py needs only a one-line import
swap.
"""

import logging
from pathlib import Path

from config import settings
from services.voice_providers.edge import EdgeVoiceProvider
from services.voice_providers.elevenlabs import ElevenLabsVoiceProvider

logger = logging.getLogger(__name__)


def get_voice_provider():
    """Resolve the active voice provider with Cosmos-style fallback."""
    name = (settings.voice_provider or "edge").lower()

    if name == "elevenlabs":
        el = ElevenLabsVoiceProvider()
        if el.is_configured():
            return el
        logger.warning("VOICE_PROVIDER=elevenlabs but ELEVENLABS_API_KEY unset — falling back to edge.")

    return EdgeVoiceProvider()


_provider = None


def _resolve():
    global _provider
    if _provider is None:
        _provider = get_voice_provider()
        logger.info(f"Active voice provider: {_provider.name}")
    return _provider


async def synthesize_narration(text: str, voice_key: str, out_path: Path) -> float:
    """Synthesize narration via the active provider.

    Signature is identical to the legacy tts.synthesize_narration so the
    pipeline orchestration code is unchanged.
    """
    provider = _resolve()
    return await provider.synthesize(text, voice_key, out_path)
