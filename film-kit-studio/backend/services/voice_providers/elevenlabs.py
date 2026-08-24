"""
ElevenLabs voice provider (cinematic tier).

Dramatically more natural and emotionally expressive than edge-tts —
realistic breath, pacing, and performance. The single biggest quality
upgrade for narration. Requires ELEVENLABS_API_KEY.

API: POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
Docs: https://elevenlabs.io/docs/api-reference/text-to-speech-v2

Voice keys: ElevenLabs uses voice IDs (e.g. "21m00Tcm4TlvDq8ikWAM") or
premade voice names. We accept either a known name -> id mapping or a
raw voice id passed as voice_key.

NOTE: Implemented to the documented ElevenLabs API. Only exercised
end-to-end when ELEVENLABS_API_KEY is set; otherwise is_configured()
returns False and the registry falls back to edge-tts.
"""

import logging
from pathlib import Path
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.elevenlabs.io"

# Friendly names -> ElevenLabs premade voice IDs (a small starter set).
# Users can also pass a raw voice ID directly as voice_key.
PRESET_VOICES: dict[str, str] = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "antoni": "ErXwobaYiN019PkySvjV",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "domi": "AZnzlk1XvdvUeBnXmlld",
    "elli": "MF3mGyEYCl7XYWbV9V6O",
    "josh": "TxGEqnHWrfWFTfGW9XjX",
    "arnold": "VR6AewLTigWG4xSOukaG",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "sam": "yoZ06aMxZJJ28mfd3POQ",
}


class ElevenLabsError(Exception):
    pass


class ElevenLabsVoiceProvider:
    """ElevenLabs TTS provider (cinematic tier)."""

    name = "elevenlabs"

    def is_configured(self) -> bool:
        return bool(settings.elevenlabs_api_key)

    def _resolve_voice_id(self, voice_key: str) -> str:
        """Resolve a friendly name or raw id to an ElevenLabs voice id."""
        key = voice_key.lower()
        if key in PRESET_VOICES:
            return PRESET_VOICES[key]
        return voice_key  # assume it's already a raw voice id

    async def synthesize(self, text: str, voice_key: str, out_path: Path) -> float:
        if not self.is_configured():
            raise ElevenLabsError("ELEVENLABS_API_KEY is not set — cannot use ElevenLabs.")

        voice_id = self._resolve_voice_id(voice_key)
        url = f"{_BASE}/v1/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        # eleven_v3 supports emotional direction via the 'audio_file_query'
        # / prosody params; for plain TTS we pass model + a stability/
        # similarity/steerability profile tuned for narration.
        payload = {
            "text": text,
            "model_id": settings.elevenlabs_model,
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True,
            },
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"[elevenlabs] voice_id={voice_id}, model={settings.elevenlabs_model}, "
                    f"text='{text[:60]}...'")

        last_exc: Optional[Exception] = None
        for attempt in range(settings.max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "20"))
                    logger.warning(f"ElevenLabs rate-limited, backing off {retry_after}s")
                    import asyncio
                    await asyncio.sleep(retry_after)
                    last_exc = ElevenLabsError("Rate limited by ElevenLabs")
                    continue
                if resp.status_code in (401, 403):
                    raise ElevenLabsError(
                        f"ElevenLabs auth error ({resp.status_code}) — check API key"
                    )
                resp.raise_for_status()

                out_path.write_bytes(resp.content)
                logger.info(f"[elevenlabs] narration saved to {out_path}")

                from utils.ffmpeg_ops import probe_duration
                duration = await probe_duration(out_path)
                logger.info(f"[elevenlabs] duration {duration:.1f}s")
                return duration

            except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                logger.warning(f"ElevenLabs error (attempt {attempt + 1}): {exc}")
                import asyncio
                await asyncio.sleep(settings.retry_delay * (attempt + 1))

        raise ElevenLabsError(
            f"ElevenLabs failed after {settings.max_retries} attempts: {last_exc}"
        )
