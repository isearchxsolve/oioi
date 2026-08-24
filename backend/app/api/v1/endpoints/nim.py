"""DEPRECATED: NVIDIA NIM endpoints removed per AC-10 (NVIDIA is a TOTAL NO-GO).

All functionality has been migrated to multi-provider endpoints:
- Chat: /api/v1/chat/completions & /api/v1/chat/stream
- Images: /api/v1/images/generations
- Videos: /api/v1/videos/generations
- Audio: /api/v1/audio/speech
- Models: /api/v1/models
- Styles: /api/v1/styles
- Health: /api/v1/providers/health
"""
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def nim_deprecated_handler(path_name: str):
    raise HTTPException(
        status_code=410,
        detail="NVIDIA NIM endpoints are deprecated and permanently removed (AC-10). Use /api/v1/{chat,images,videos,audio,models,styles,providers} instead.",
    )