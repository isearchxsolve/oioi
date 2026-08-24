"""
Kling 3.0 visual provider (first-party API).

Kling is a strong cinematic option, especially for long-form and
image-to-video. Accessed via api.klingai.com with JWT authentication
signed from KLING_API_KEY + KLING_API_SECRET.

API shape (async task):
  1. POST .../v1/videos/text2video   → returns task id
  2. GET  .../v1/videos/text2video/{id}  → poll until status == succeed
  3. response.data.videos[0].resource.url → download the MP4

Docs: https://klingai.com/document-api

NOTE: Implemented to the documented Kling API. Only exercised end-to-end
when both KLING_API_KEY and KLING_API_SECRET are set; otherwise
is_configured() returns False and the registry falls back.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from config import ASPECTS, settings
from services.visual_providers.base import ProgressCallback
from utils.token_bucket import TokenBucket

logger = logging.getLogger(__name__)

_kling_bucket = TokenBucket(rpm=10.0, min_gap=2.0)


class KlingError(Exception):
    pass


def _make_jwt() -> str:
    """Sign a short-lived HS256 JWT for Kling from the API key + secret."""
    import base64
    import hashlib
    import hmac
    import json

    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iss": settings.kling_api_key,
        "exp": now + 1800,  # 30 min
        "nbf": now - 5,
    }

    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(obj, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()

    signing_input = f"{b64(header)}.{b64(payload)}".encode()
    sig = hmac.new(
        settings.kling_api_secret.encode(), signing_input, hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{signing_input.decode()}.{sig_b64}"


def _aspect_to_kling_ratio(aspect: str) -> str:
    """Map our aspect string to Kling's accepted ratio strings."""
    w, h = ASPECTS.get(aspect, ASPECTS["16:9"])
    if h > w:
        return "9:16"
    if abs(w - h) < 10:
        return "1:1"
    return "16:9"


class KlingVisualProvider:
    """Kling 3.0 provider (cinematic tier)."""

    name = "kling"

    def is_configured(self) -> bool:
        return bool(settings.kling_api_key and settings.kling_api_secret)

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
            raise KlingError("KLING_API_KEY / KLING_API_SECRET not set — cannot use Kling.")

        await _kling_bucket.wait()

        headers = {
            "Authorization": f"Bearer {_make_jwt()}",
            "Content-Type": "application/json",
        }

        # Kling duration must be one of 5 or 10 (seconds)
        kling_duration = 10 if duration_seconds > 5 else 5
        payload: dict[str, Any] = {
            "model": "kling-v2-master",  # Kling 3.0 master tier
            "prompt": visual_prompt,
            "duration": kling_duration,
            "aspect_ratio": _aspect_to_kling_ratio(aspect),
        }
        if seed is not None:
            payload["seed"] = seed

        # ControlNet conditioning
        if controlnet_images:
            controlnet_conditioning = []
            for cn_type, cn_path in controlnet_images.items():
                if cn_path and cn_path.exists():
                    import base64
                    cn_bytes = cn_path.read_bytes()
                    controlnet_conditioning.append({
                        "type": cn_type,  # canny, depth, pose, normal, lineart
                        "image": base64.b64encode(cn_bytes).decode("utf-8"),
                        "scale": 1.0,
                    })
            if controlnet_conditioning:
                payload["controlnet_conditioning"] = controlnet_conditioning

        # LoRA support
        if lora_path:
            payload["lora"] = {
                "path": lora_path,
                "scale": lora_scale,
            }

        # Choose endpoint based on reference image
        if reference_image:
            import base64
            image_bytes = reference_image.read_bytes()
            payload["image"] = base64.b64encode(image_bytes).decode("utf-8")
            create_url = f"{settings.kling_base_url}/v1/videos/image2video"
            mode = "image2video"
        else:
            create_url = f"{settings.kling_base_url}/v1/videos/text2video"
            mode = "text2video"

        # 1. Submit task
        task_id: Optional[str] = None
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                if progress_callback:
                    await progress_callback(0.05, f"Submitting to Kling {mode} (attempt {attempt + 1})...")
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(create_url, headers=headers, json=payload)

                if resp.status_code == 429:
                    _kling_bucket.penalize()
                    await asyncio.sleep(float(resp.headers.get("Retry-After", "30")))
                    last_exc = KlingError("Rate limited by Kling")
                    continue
                if resp.status_code in (401, 403):
                    raise KlingError(f"Kling auth error ({resp.status_code}) — check credentials")
                resp.raise_for_status()

                data = resp.json().get("data", {})
                task_id = data.get("task_id")
                if not task_id:
                    raise KlingError(f"No task_id in Kling response: {data}")
                break
            except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                logger.warning(f"Kling submit error (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(settings.retry_delay * (attempt + 1))
        else:
            raise KlingError(f"Kling submit failed after {max_retries} attempts: {last_exc}")

        # 2. Poll task
        poll_url = f"{create_url}/{task_id}"
        deadline = 600.0
        elapsed = 0.0
        interval = 10.0
        async with httpx.AsyncClient(timeout=120.0) as client:
            while elapsed < deadline:
                if progress_callback:
                    await progress_callback(
                        min(0.9, 0.1 + elapsed / deadline * 0.8),
                        "Kling generating video...",
                    )
                resp = await client.get(poll_url, headers=headers)
                resp.raise_for_status()
                body = resp.json().get("data", {})
                status = body.get("task_status", "").lower()
                if status in ("succeed", "success", "done"):
                    return await self._download(body, out_path, progress_callback)
                if status in ("failed", "error"):
                    raise KlingError(f"Kling task failed: {body.get('task_status_msg')}")
                await asyncio.sleep(interval)
                elapsed += interval

        raise KlingError("Kling generation timed out.")

    async def _download(
        self,
        body: dict[str, Any],
        out_path: Path,
        progress_callback: ProgressCallback,
    ) -> str:
        videos = body.get("videos") or []
        if not videos:
            raise KlingError(f"No videos in completed Kling task: {body}")
        url = videos[0].get("url")
        if not url:
            raise KlingError(f"No resource URL in Kling video: {videos[0]}")

        if progress_callback:
            await progress_callback(0.95, "Downloading Kling video...")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=180.0) as client:
            dl = await client.get(url)
            dl.raise_for_status()
            out_path.write_bytes(dl.content)

        if progress_callback:
            await progress_callback(1.0, "Kling video generated")
        logger.info(f"Kling video saved to {out_path}")
        return str(out_path)