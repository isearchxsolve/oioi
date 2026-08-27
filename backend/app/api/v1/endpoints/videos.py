"""Video generation endpoint.

History worth knowing before changing this file. It used to call
`adapter.generate_video(prompt=..., model=...)`, but every adapter in providers/ takes a single
`VideoGenerationRequest` object -- so the call raised TypeError on the first argument, was caught by
a blanket `except Exception: pass`, and fell through to

    https://cdn.pollinations.ai/video/clip_<prompt>.mp4   with "status": "completed"

MEASURED 2026-08-24: that host does not resolve (getaddrinfo failed). So this endpoint reported
success for every request it ever served while returning a URL that was never a video, and the
mismatch that guaranteed it was invisible because the exception was discarded.

Both are fixed here: the real contract is used, and a failure is reported as a failure.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.api.v1.endpoints.legacy import require_legacy_demo_mode
from app.services.provider_service import get_provider_registry
from providers.base import VideoGenerationRequest as ProviderVideoRequest

router = APIRouter()


class VideoGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    first_frame_url: Optional[str] = None
    last_frame_url: Optional[str] = None
    duration_seconds: Optional[int] = 5


@router.post("/generations")
async def generate_video(request: VideoGenerationRequest):
    """Generate one real video clip through the highest-priority video provider.

    SPENDS REAL CREDITS when omniroute_video serves the request: a Flow clip quotes 20 credits and
    an rtst clip 6, from a finite balance that no API tops up. The adapter quotes first and refuses
    anything over settings.OMNIROUTE_VIDEO_MAX_CREDITS, and it never retries a submitted job.

    Note the absence of a retry or a fallback loop here. For text or images, trying the next
    provider costs nothing. For video it can cost twice: a submit that times out may still be
    running and still be charging, so a second attempt buys a second clip. One provider, one
    attempt, and an honest error.
    """
    require_legacy_demo_mode()
    registry = await get_provider_registry()

    try:
        adapter = await registry.get_adapter("video")
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"no video provider is registered: {exc}",
        ) from exc

    name = adapter.get_provider_name()
    provider_request = ProviderVideoRequest(
        prompt=request.prompt,
        model=request.model or settings.DEFAULT_VIDEO_MODEL,
        first_frame=request.first_frame_url,
        last_frame=request.last_frame_url,
    )

    try:
        result = await adapter.generate_video(provider_request)
    except NotImplementedError as exc:
        # The honest shape of "this provider was registered for video but cannot do video".
        # GeminiAdapter.generate_video is exactly this. Reported, not hidden.
        registry.report_failure(name, reason="generate_video not implemented")
        raise HTTPException(
            status_code=501,
            detail=f"provider {name!r} does not implement video generation: {exc}",
        ) from exc
    except Exception as exc:
        registry.report_failure(name, reason=str(exc)[:200])
        raise HTTPException(
            status_code=502,
            detail=f"video generation failed via {name!r}: {type(exc).__name__}: {exc}",
        ) from exc

    registry.report_success(name)

    clips: List[Dict[str, Any]] = list(result.data or [])
    if not clips:
        raise HTTPException(
            status_code=502,
            detail=f"provider {name!r} reported success but returned no clip",
        )
    first = clips[0]

    return {
        "status": "completed",
        # Kept for the existing frontend, which reads video_url.
        "video_url": first.get("url"),
        "provider": name,
        "prompt": request.prompt,
        "first_frame": request.first_frame_url,
        "last_frame": request.last_frame_url,
        # What it cost and where it landed. Absent on providers that do not report them.
        "credits_charged": first.get("credits_charged"),
        "local_path": first.get("path"),
        "job_id": first.get("job_id"),
        "created": result.created,
        "data": clips,
    }


@router.get("/providers")
async def video_providers():
    """Which providers could serve a video request, and is the paid one actually reachable.

    Free: no generation, no credits. This is the route a UI should call before offering a Generate
    button, so the user is told "the router is not running" instead of discovering it 90 seconds
    into a failed render.
    """
    registry = await get_provider_registry()
    out: List[Dict[str, Any]] = []
    for pname in registry.list_providers():
        rec = registry.get(pname)
        if not rec or "video" not in (rec.capabilities or ()):
            continue
        entry: Dict[str, Any] = {"name": pname, "priority": rec.priority}
        if pname == "omniroute_video":
            from providers.omniroute_video import OmniRouteVideoAdapter
            probe = OmniRouteVideoAdapter(
                base_url=settings.OMNIROUTE_VIDEO_BASE_URL,
                api_key=settings.OMNIROUTE_VIDEO_TOKEN,
                max_credits=settings.OMNIROUTE_VIDEO_MAX_CREDITS,
            )
            entry["reachable"] = probe.is_configured()
            entry["base_url"] = settings.OMNIROUTE_VIDEO_BASE_URL
            entry["max_credits"] = settings.OMNIROUTE_VIDEO_MAX_CREDITS
            entry["health"] = (await probe.health_check()).model_dump()
            await probe.aclose()
        out.append(entry)
    return {"providers": out}
