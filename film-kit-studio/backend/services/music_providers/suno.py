"""
Suno music provider (cinematic tier), via a gateway API.

Suno produces real, listenable instrumental scores — a massive step up
from the synthesised FFMPEG bed. Suno has no official self-serve API as
of mid-2026, so this targets a configurable gateway provider
(SUNO_BASE_URL, defaulting to a musicapi.ai-style REST surface).

Gateway API shape (async, varies by provider — this implements a common
contract):
  1. POST {base}/suno/generate   { prompt, instrumental: true }  → task id
  2. GET  {base}/suno/tasks/{id}  → poll until status done
  3. response.audio_url          → download the MP3

NOTE: Implemented to the documented gateway contract. Only exercised
end-to-end when SUNO_API_KEY is set; otherwise is_configured() returns
False and the registry falls back to the free FFMPEG bed. Users may need
to adjust endpoints/payload to match their specific gateway provider.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Mood -> Suno prompt phrasing. We keep it instrumental so it sits under
# narration without competing with a vocal.
_MOOD_PROMPTS: dict[str, str] = {
    "ambient": "ambient cinematic instrumental, slow, spacious, warm pads, no drums",
    "tense": "tense cinematic instrumental, low drones, dissonant strings, suspenseful",
    "bright": "uplifting cinematic instrumental, bright, hopeful, gentle piano and strings",
}


class SunoError(Exception):
    pass


class SunoMusicProvider:
    """Suno score provider via a gateway (cinematic tier)."""

    name = "suno"

    def is_configured(self) -> bool:
        return bool(settings.suno_api_key)

    async def generate(self, duration: float, out_path: Path, mood: str = "ambient") -> Path:
        if not self.is_configured():
            raise SunoError("SUNO_API_KEY is not set — cannot use Suno provider.")

        headers = {
            "Authorization": f"Bearer {settings.suno_api_key}",
            "Content-Type": "application/json",
        }

        prompt = _MOOD_PROMPTS.get(mood, _MOOD_PROMPTS["ambient"])
        payload = {
            "prompt": prompt,
            "instrumental": True,
            "model": "suno-v5",
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        base = settings.suno_base_url.rstrip("/")

        # 1. Submit generation
        task_id: Optional[str] = None
        last_exc: Optional[Exception] = None
        for attempt in range(settings.max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(f"{base}/suno/generate", headers=headers, json=payload)

                if resp.status_code == 429:
                    await asyncio.sleep(float(resp.headers.get("Retry-After", "20")))
                    last_exc = SunoError("Rate limited by Suno gateway")
                    continue
                if resp.status_code in (401, 403):
                    raise SunoError(f"Suno gateway auth error ({resp.status_code}) — check key")
                resp.raise_for_status()

                data = resp.json().get("data", resp.json())
                task_id = data.get("task_id") or data.get("id")
                if not task_id:
                    raise SunoError(f"No task id from Suno gateway: {data}")
                break
            except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                logger.warning(f"Suno submit error (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(settings.retry_delay * (attempt + 1))
        else:
            raise SunoError(f"Suno submit failed after {settings.max_retries} attempts: {last_exc}")

        # 2. Poll
        poll_url = f"{base}/suno/tasks/{task_id}"
        deadline = 300.0
        elapsed = 0.0
        audio_url: Optional[str] = None
        async with httpx.AsyncClient(timeout=120.0) as client:
            while elapsed < deadline:
                resp = await client.get(poll_url, headers=headers)
                resp.raise_for_status()
                body = resp.json().get("data", resp.json())
                status = str(body.get("status", "")).lower()
                if status in ("completed", "succeed", "success", "done"):
                    audio_url = body.get("audio_url") or (
                        body.get("output", [{}])[0].get("audio_url") if body.get("output") else None
                    )
                    if not audio_url:
                        raise SunoError(f"Suno task done but no audio_url: {body}")
                    break
                if status in ("failed", "error"):
                    raise SunoError(f"Suno task failed: {body}")
                await asyncio.sleep(8.0)
                elapsed += 8.0

        if not audio_url:
            raise SunoError("Suno generation timed out.")

        # 3. Download
        async with httpx.AsyncClient(timeout=180.0) as client:
            dl = await client.get(audio_url)
            dl.raise_for_status()
            out_path.write_bytes(dl.content)

        logger.info(f"[suno] score ({mood}) saved to {out_path}")
        return out_path
