"""Retired direct image-generation compatibility route.

The merged consumer contract currently exposes text and video through the
OpenAI-shaped ``:8190/v1`` surface.  This legacy image endpoint used to call
OiiOii's in-process provider registry and an external fallback, so it could
bypass the consumer gateway.  Keep the request shape for stale clients but fail
closed until a canonical image contract is deliberately added.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.endpoints.legacy import require_legacy_demo_mode
from app.models.user import User

router = APIRouter()


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = "pollinations/flux"
    size: Optional[str] = "1024x1024"
    n: Optional[int] = 1
    style: Optional[str] = None


@router.post("/generations")
async def generate_images(
    request: ImageGenerationRequest,
    user: User = Depends(get_current_user),
) -> None:
    """Reject direct image generation rather than bypassing ``:8190``."""

    del request, user
    require_legacy_demo_mode()
