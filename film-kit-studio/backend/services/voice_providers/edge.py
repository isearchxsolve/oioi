"""
Microsoft edge-tts voice provider (the free default).

Re-locates the logic previously in services/tts.py behind the
VoiceProvider protocol. Keyless, zero-cost, decent quality — but reads
as TTS rather than performance. Kept as the out-of-the-box default so
the pipeline works with no API keys.
"""

import logging
from pathlib import Path

import edge_tts

from config import VOICES

logger = logging.getLogger(__name__)


class EdgeVoiceProvider:
    """Microsoft edge-tts provider (free default)."""

    name = "edge"

    def is_configured(self) -> bool:
        # edge-tts is keyless, always available.
        return True

    async def synthesize(self, text: str, voice_key: str, out_path: Path) -> float:
        voice = VOICES.get(voice_key, voice_key)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"[edge-tts] voice={voice}, text='{text[:60]}...'")

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))

        # Probe duration (imported lazily to avoid a circular import)
        from utils.ffmpeg_ops import probe_duration

        duration = await probe_duration(out_path)
        logger.info(f"[edge-tts] narration saved to {out_path} ({duration:.1f}s)")
        return duration
