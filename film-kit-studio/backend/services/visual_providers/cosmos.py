"""
NVIDIA Cosmos3 NIM visual provider (the free default).

Re-locates the logic previously in services/nim_cosmos.py behind the
VisualProvider protocol. Cosmos is a Physical-AI world foundation model —
it works keylessly against the NIM endpoint given an NIM_API_KEY, but its
output is not specifically cinematic; it is the zero-cost fallback that
keeps the pipeline running when no higher-tier key is configured.
"""

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from config import ASPECTS, settings
from services.visual_providers.base import ProgressCallback
from utils.token_bucket import TokenBucket

logger = logging.getLogger(__name__)

# Separate token bucket for Cosmos (may have different RPM limits)
_cosmos_bucket = TokenBucket(rpm=min(settings.nim_rpm, 20.0), min_gap=2.0)


class CosmosError(Exception):
    pass


class CosmosRateLimitError(CosmosError):
    pass


def _get_resolution(aspect: str, quality: str = "standard") -> tuple[int, int]:
    """(width, height) for the given aspect, scaled by quality tier."""
    base_w, base_h = ASPECTS.get(aspect, ASPECTS["16:9"])
    if quality == "standard":
        return base_w // 2, base_h // 2
    return base_w, base_h


def _extract_media_from_response(data: dict[str, Any]) -> Optional[str | bytes]:
    """Extract media (base64 / url / bytes) from a Cosmos3 response — robust
    against the several response shapes NIM may return."""
    if "video" in data:
        return data["video"]
    artifacts = data.get("artifacts", [])
    if artifacts and isinstance(artifacts, list):
        first = artifacts[0]
        if isinstance(first, dict):
            if "base64" in first:
                return first["base64"]
            if "url" in first:
                return first["url"]
    output = data.get("output", {})
    if isinstance(output, dict):
        for key in ("video", "url", "base64"):
            if key in output:
                return output[key]
    data_list = data.get("data", [])
    if data_list and isinstance(data_list, list):
        first = data_list[0]
        if isinstance(first, dict):
            if "b64_json" in first:
                return first["b64_json"]
            if "url" in first:
                return first["url"]
    if "b64_json" in data:
        return data["b64_json"]
    if "url" in data:
        return data["url"]
    return None


class CosmosVisualProvider:
    """NVIDIA Cosmos3 NIM provider (free default)."""

    name = "cosmos"

    def is_configured(self) -> bool:
        # NIM_API_KEY doubles as the key for both LLM and Cosmos.
        return bool(settings.nim_api_key)

    async def generate(
        self,
        visual_prompt: str,
        out_path: Path,
        aspect: str = "16:9",
        seed: Optional[int] = None,
        duration_seconds: float = 4.0,
        max_retries: int = 3,
        progress_callback: ProgressCallback = None,
        reference_image: Optional[Path] = None,
        controlnet_images: Optional[dict[str, Path]] = None,
        lora_path: Optional[str] = None,
        lora_scale: float = 1.0,
    ) -> str:
        await _cosmos_bucket.wait()

        width, height = _get_resolution(aspect, quality="standard")

        headers = {
            "Authorization": f"Bearer {settings.nim_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Choose mode based on reference image
        mode = "IMAGE2WORLD" if reference_image else "TEXT2WORLD"
        
        payload: dict[str, Any] = {
            "model": settings.nim_cosmos_model,
            "mode": mode,
            "prompt": visual_prompt,
            "width": width,
            "height": height,
            "seed": seed if seed is not None else int(time.time()) % 1_000_000,
            "num_frames": int(duration_seconds * settings.fps_default),
            "fps": settings.fps_default,
        }

        if reference_image:
            import base64
            image_bytes = reference_image.read_bytes()
            payload["image"] = base64.b64encode(image_bytes).decode("utf-8")

        # ControlNet conditioning for Cosmos (IMAGE2WORLD mode)
        if controlnet_images and mode == "IMAGE2WORLD":
            payload["controlnet_images"] = {}
            for cn_type, cn_path in controlnet_images.items():
                if cn_path and cn_path.exists():
                    import base64
                    cn_bytes = cn_path.read_bytes()
                    payload["controlnet_images"][cn_type] = base64.b64encode(cn_bytes).decode("utf-8")

        # LoRA conditioning (if supported by endpoint)
        if lora_path:
            payload["lora_path"] = lora_path
            payload["lora_scale"] = lora_scale

        url = settings.nim_infer_url
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                if progress_callback:
                    await progress_callback(0.1, f"Calling Cosmos3 NIM {mode} (attempt {attempt + 1})...")

                logger.info(
                    f"Cosmos3 request: mode={mode} prompt='{visual_prompt[:60]}...' "
                    f"size={width}x{height} seed={payload['seed']}"
                )

                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code == 429:
                    logger.warning("Cosmos3 rate-limited (429) — backing off")
                    _cosmos_bucket.penalize()
                    retry_after = float(resp.headers.get("Retry-After", "90"))
                    await asyncio.sleep(retry_after)
                    last_exc = CosmosRateLimitError("Rate limited by Cosmos3 NIM")
                    continue

                if resp.status_code in (401, 403):
                    raise CosmosError(
                        f"Cosmos3 authentication error ({resp.status_code}) — check your API key"
                    )

                resp.raise_for_status()
                data = resp.json()

                if progress_callback:
                    await progress_callback(0.7, "Received response, extracting media...")

                media_data = _extract_media_from_response(data)
                if media_data is None:
                    raise CosmosError("No media data in Cosmos3 response")

                if progress_callback:
                    await progress_callback(0.9, "Writing media file...")

                out_path.parent.mkdir(parents=True, exist_ok=True)

                if isinstance(media_data, bytes):
                    out_path.write_bytes(media_data)
                elif isinstance(media_data, str) and media_data.startswith("http"):
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        media_resp = await client.get(media_data)
                        media_resp.raise_for_status()
                        out_path.write_bytes(media_resp.content)
                else:
                    out_path.write_bytes(base64.b64decode(media_data))

                if progress_callback:
                    await progress_callback(1.0, "Visual generated successfully")

                logger.info(f"Cosmos3 visual saved to {out_path}")
                return str(out_path)

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code == 429:
                    continue
                logger.warning(f"Cosmos3 HTTP error (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(settings.retry_delay * (attempt + 1))

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning(f"Cosmos3 network error (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(settings.retry_delay * (attempt + 1))

        raise CosmosError(
            f"Cosmos3 NIM failed after {max_retries} attempts. Last error: {last_exc}"
        )
