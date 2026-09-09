"""Video routes kept for compatibility with the retired pre-SaaS API.

Customer video work belongs to the durable ``/films`` graph.  The old
``/videos/generations`` route is therefore a permanent 410 and never imports a
provider registry.  The read-only ``/videos/providers`` view is still useful to
the UI, but it discovers advertised routes through the canonical consumer
catalogue rather than probing the retired ``:8189`` router.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.endpoints.legacy import require_legacy_demo_mode
from app.api.v1.dependencies.auth import get_current_user
from app.models.user import User
from film_pipeline.clients import ChatPoolClient

router = APIRouter()


class VideoGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    first_frame_url: Optional[str] = None
    last_frame_url: Optional[str] = None
    duration_seconds: Optional[int] = 5


@router.post("/generations")
async def generate_video(
    request: VideoGenerationRequest,
    user: User = Depends(get_current_user),
) -> None:
    """Reject the old direct-provider generation surface permanently."""

    del request, user
    require_legacy_demo_mode()


@router.get("/providers")
async def video_providers(user: User = Depends(get_current_user)):
    """List canonical video routes without spending or probing a provider.

    The response is sourced from ``GET http://127.0.0.1:8190/v1/models``.  A
    model row is an advertised route, not proof of a graduated seat; actual
    generation remains behind the durable film scheduler.
    """

    del user
    client = ChatPoolClient()
    try:
        catalogue = await client.models()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"canonical video catalogue unavailable: {type(exc).__name__}") from exc
    finally:
        await client.aclose()

    routes = sorted({
        str(row.get("id"))
        for row in (catalogue.get("data") or [])
        if isinstance(row, dict) and str(row.get("id") or "").startswith("video/")
        and str(row.get("id")) != "video/auto"
    })
    return {
        "transport": "http://127.0.0.1:8190/v1",
        "providers": [
            {"name": route.removeprefix("video/").removesuffix("/auto"), "route": route, "reachable": True}
            for route in routes
        ],
    }
