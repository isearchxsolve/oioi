"""
Google Veo 3.1 visual provider (via the Gemini API).

Veo is the strongest cinematic option: high-fidelity video with native
audio, shot composition that reads as filmic. Accessed through Google's
generativelanguage REST API.

API shape (long-running operation):
  1. POST .../models/{model}:predictLongRunning  → returns operation name
  2. GET  .../{operation}                         → poll until done:true
  3. response.generatedSamples[].video.uri        → download the MP4

Docs: https://ai.google.dev/gemini-api/docs/video

NOTE: This is implemented to the documented Gemini video-generation API.
It is only exercised end-to-end when GEMINI_API_KEY is set; without it
is_configured() returns False and the registry falls back to Cosmos.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from config import ASPECTS, settings
from services.visual_providers.base import ProgressCallback
from utils.token_bucket import TokenBucket

logger = logging.getLogger(__name__)

_veo_bucket = TokenBucket(rpm=10.0, min_gap=2.0)  # Veo RPM is lower than Cosmos

_BASE = "https://generativelanguage.googleapis.com"


class VeoError(Exception):
    pass


def _aspect_to_veo_image_config(aspect: str) -> dict[str, Any]:
    """Map our aspect string to Veo's imageConfig (aspectRatio + resolution)."""
    w, h = ASPECTS.get(aspect, ASPECTS["16:9"])
    if w >= h:
        ratio = "16:9" if abs(w / h - 16 / 9) < 0.1 else "9:16" if h > w else "1:1"
    else:
        ratio = "9:16"
    # Veo accepts "16:9" | "9:16"
    return {"aspectRatio": ratio, "resolution": "720p"}


class VeoVisualProvider:
    """Google Veo 3.1 via the Gemini API (cinematic tier)."""

    name = "veo"

    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    async def generate(
        self,
        visual_prompt: str,
        out_path: Path,
        aspect: str = "16:9",
        seed: Optional[int] = None,
        duration_seconds: float = 5.0,
        max_retries: int = 3,
        progress_callback: ProgressCallback = None,
        reference_image: Optional[Path] = None,
        controlnet_images: Optional[dict[str, Path]] = None,
        lora_path: Optional[str] = None,
        lora_scale: float = 1.0,
    ) -> str:
        if not self.is_configured():
            raise VeoError("GEMINI_API_KEY is not set — cannot use Veo provider.")

        await _veo_bucket.wait()

        headers = {
            "x-goog-api-key": settings.gemini_api_key,
            "Content-Type": "application/json",
        }

        image_config = _aspect_to_veo_image_config(aspect)
        
        # Build instance - add image field for image-to-video
        instance = {
            "prompt": visual_prompt,
            "imageConfig": image_config,
        }
        
        if reference_image:
            import base64
            image_bytes = reference_image.read_bytes()
            instance["image"] = {
                "bytesBase64Encoded": base64.b64encode(image_bytes).decode("utf-8"),
            }

        # ControlNet conditioning for Veo
        if controlnet_images:
            # Veo uses control_video_reference + control_type
            # For now, use the first controlnet image as reference
            for cn_type, cn_path in controlnet_images.items():
                if cn_path and cn_path.exists():
                    import base64
                    cn_bytes = cn_path.read_bytes()
                    cn_type_upper = cn_type.upper()
                    instance["controlVideoReference"] = {
                        "bytesBase64Encoded": base64.b64encode(cn_bytes).decode("utf-8"),
                        "controlType": cn_type_upper,  # CANNY, DEPTH, POSE, NORMAL, LINEART
                    }
                    break  # Use first for now

        # LoRA (Veo doesn't natively support LoRA yet, but pass in prompt if needed)
        if lora_path:
            # Add as metadata for future support
            instance["loraPath"] = lora_path
            instance["loraScale"] = lora_scale
        
        instances = [instance]
        predict_payload: dict[str, Any] = {
            "instances": instances,
            "parameters": {"sampleCount": 1},
        }

        url = f"{_BASE}/v1beta/models/{settings.veo_model}:predictLongRunning"

        # 1. Submit the long-running generation
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                mode = "image2video" if reference_image else "text2video"
                if progress_callback:
                    await progress_callback(0.05, f"Submitting to Veo {mode} (attempt {attempt + 1})...")
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(url, headers=headers, json=predict_payload)

                if resp.status_code == 429:
                    _veo_bucket.penalize()
                    retry_after = float(resp.headers.get("Retry-After", "30"))
                    await asyncio.sleep(retry_after)
                    last_exc = VeoError("Rate limited by Veo")
                    continue
                if resp.status_code in (401, 403):
                    raise VeoError(f"Veo auth error ({resp.status_code}) — check GEMINI_API_KEY")
                resp.raise_for_status()

                op_data = resp.json()
                operation = op_data.get("name")
                if not operation:
                    raise VeoError(f"No operation name in Veo response: {op_data}")
                break
            except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                logger.warning(f"Veo submit error (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(settings.retry_delay * (attempt + 1))
        else:
            raise VeoError(f"Veo submit failed after {max_retries} attempts: {last_exc}")

        # 2. Poll the operation
        op_url = f"{_BASE}/v1beta/{operation}"
        deadline = 600.0  # Veo can take a few minutes
        elapsed = 0.0
        interval = 10.0
        async with httpx.AsyncClient(timeout=120.0) as client:
            while elapsed < deadline:
                if progress_callback:
                    await progress_callback(
                        min(0.9, 0.1 + elapsed / deadline * 0.8),
                        "Veo generating video...",
                    )
                resp = await client.get(op_url, headers=headers)
                resp.raise_for_status()
                op_state = resp.json()
                if op_state.get("done"):
                    if "error" in op_state:
                        raise VeoError(f"Veo operation failed: {op_state['error']}")
                    return await self._download_video(
                        op_state, out_path, headers, progress_callback
                    )
                await asyncio.sleep(interval)
                elapsed += interval

        raise VeoError("Veo generation timed out.")

    async def _download_video(
        self,
        op_state: dict[str, Any],
        out_path: Path,
        headers: dict[str, str],
        progress_callback: ProgressCallback,
    ) -> str:
        """Extract the generated video URI and download it to out_path."""
        resp = op_state.get("response", {})
        samples = resp.get("generatedSamples") or resp.get("videos") or []
        if not samples:
            # Fall back to other known shapes
            videos = resp.get("videos", [])
            samples = videos
        if not samples:
            raise VeoError(f"No generated video in Veo response: {resp}")

        first = samples[0]
        video = first.get("video", first) if isinstance(first, dict) else {}
        uri = video.get("uri") or first.get("uri") if isinstance(first, dict) else None
        if not uri:
            raise VeoError(f"No video URI in Veo sample: {first}")

        if progress_callback:
            await progress_callback(0.95, "Downloading Veo video...")

        # Veo video URIs include an auth-enforced download URL
        download_url = uri if uri.startswith("http") else f"{_BASE}{uri}"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=180.0) as client:
            dl = await client.get(download_url, headers=headers)
            dl.raise_for_status()
            out_path.write_bytes(dl.content)

        if progress_callback:
            await progress_callback(1.0, "Veo video generated")
        logger.info(f"Veo video saved to {out_path}")
        return str(out_path)
