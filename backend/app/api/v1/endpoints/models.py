"""Authenticated model discovery backed by the canonical consumer catalogue."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.dependencies.auth import get_current_user
from app.models.user import User
from film_pipeline.clients import ChatPoolClient


CANONICAL_CONSUMER_BASE_URL = "http://127.0.0.1:8190/v1"
router = APIRouter()


def _safe_route(row: Any) -> Dict[str, Any] | None:
    """Keep only customer-safe catalogue metadata, never upstream URLs or keys."""

    if not isinstance(row, dict):
        return None
    route = str(row.get("id") or "").strip()
    if not route:
        return None
    is_video = route.startswith("video/")
    provider = str(row.get("provider") or row.get("owned_by") or "session_pool").strip() or "session_pool"
    return {
        "id": route,
        "name": str(row.get("name") or route.replace("/", " ").replace("-", " ").title()),
        "provider": provider,
        "category": "Video" if is_video else "LLM",
        "capabilities": ["video"] if is_video else ["chat"],
        "enabled": True,
    }


async def _canonical_catalogue() -> Dict[str, Any]:
    client = None
    try:
        client = ChatPoolClient()
        catalogue = await client.models()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"canonical model catalogue unavailable: {type(exc).__name__}",
        ) from exc
    finally:
        if client is not None:
            await client.aclose()

    by_id: Dict[str, Dict[str, Any]] = {}
    for row in catalogue.get("data") or []:
        safe = _safe_route(row)
        if safe is not None:
            # A route ID is the stable consumer handle. Keep the first row so a
            # duplicate upstream entry cannot inflate capacity in the UI.
            by_id.setdefault(safe["id"], safe)

    rows = list(by_id.values())
    video_models = sorted((row for row in rows if row["category"] == "Video"), key=lambda row: row["id"])
    llm_models = sorted((row for row in rows if row["category"] == "LLM"), key=lambda row: row["id"])
    # Images are intentionally absent from the canonical consumer contract. The
    # old image adapters were retired; returning an empty list is more truthful
    # than exposing static routes that the app cannot execute.
    image_models: List[Dict[str, Any]] = []
    return {
        "categories": ["Video", "Image", "LLM"],
        "counts": {
            "Video": len(video_models),
            "Image": len(image_models),
            "LLM": len(llm_models),
            "Total": len(rows),
        },
        "video_models": video_models,
        "image_models": image_models,
        "llm_models": llm_models,
        "transport": CANONICAL_CONSUMER_BASE_URL,
        "catalogue_only": True,
    }


@router.get("/")
async def list_models(user: User = Depends(get_current_user)):
    """List routes advertised by the authenticated canonical consumer gateway."""

    del user
    return await _canonical_catalogue()


@router.get("/category/{category}")
async def get_models_for_category(category: str, user: User = Depends(get_current_user)):
    """Filter the canonical catalogue without exposing a direct provider surface."""

    del user
    catalogue = await _canonical_catalogue()
    key = {"video": "video_models", "image": "image_models", "llm": "llm_models"}.get(category.lower())
    if key is None:
        return []
    return catalogue[key]
