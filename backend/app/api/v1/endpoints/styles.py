from fastapi import APIRouter
from typing import List, Dict, Any, Optional

from styles_registry import STYLES, count_by_category, filter_by_category

router = APIRouter()


@router.get("/")
async def list_styles(category: Optional[str] = None):
    """List 150+ visual animation styles (AC-5, AC-11)."""
    if category:
        return {
            "category": category,
            "styles": filter_by_category(STYLES, category),
            "count": len(filter_by_category(STYLES, category)),
        }
    return {
        "styles": STYLES,
        "total": len(STYLES),
        "counts": count_by_category(STYLES),
    }
