from fastapi import APIRouter
from typing import List, Dict, Any

from models_registry import VIDEO_MODELS, IMAGE_MODELS, LLM_MODELS, get_models_by_category, count_models_by_category

router = APIRouter()


@router.get("/")
async def list_models():
    """List 25+ models grouped by Video, Image, LLM categories (AC-4, AC-12)."""
    return {
        "categories": ["Video", "Image", "LLM"],
        "counts": count_models_by_category(),
        "video_models": VIDEO_MODELS,
        "image_models": IMAGE_MODELS,
        "llm_models": LLM_MODELS,
    }


@router.get("/category/{category}")
async def get_models_for_category(category: str):
    """Filter models by category."""
    return get_models_by_category(category)
