"""
FFMPEG synthesised ambient bed (the free default).

Thin wrapper around utils.ffmpeg_ops.generate_ambient_bed so it conforms
to the MusicProvider protocol. The bed itself (chord pad + tremolo +
stereo widening) is the enriched free tier.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FfmpegMusicProvider:
    """Synthesised ambient-bed score provider (free default)."""

    name = "ffmpeg"

    def is_configured(self) -> bool:
        return True

    async def generate(self, duration: float, out_path: Path, mood: str = "ambient") -> Path:
        from utils.ffmpeg_ops import generate_ambient_bed

        out_path.parent.mkdir(parents=True, exist_ok=True)
        await generate_ambient_bed(duration, out_path, mood)
        logger.info(f"[ffmpeg] ambient bed ({mood}) saved to {out_path}")
        return out_path
