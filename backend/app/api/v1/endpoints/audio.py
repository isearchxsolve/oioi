"""Retired direct audio-generation compatibility route.

Audio generation previously returned a third-party URL without going through the
authenticated consumer boundary.  The route remains mounted only to return an
explicit migration response; it never calls a provider or fabricates a completed
artifact.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.endpoints.legacy import require_legacy_demo_mode
from app.models.user import User

router = APIRouter()


class AudioSpeechRequest(BaseModel):
    input: str
    voice: Optional[str] = "alloy"
    model: Optional[str] = "tts-1"


@router.post("/speech")
async def generate_speech(
    request: AudioSpeechRequest,
    user: User = Depends(get_current_user),
) -> None:
    """Reject direct speech generation rather than bypassing ``:8190``."""

    del request, user
    require_legacy_demo_mode()
