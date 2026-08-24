from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.services.provider_service import get_provider_registry

router = APIRouter()


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = "pollinations/flux"
    size: Optional[str] = "1024x1024"
    n: Optional[int] = 1
    style: Optional[str] = None


@router.post("/generations")
async def generate_images(request: ImageGenerationRequest):
    """Generate images via free-tier provider (Pollinations keyless / Cloudflare / Gemini)."""
    registry = await get_provider_registry()
    full_prompt = request.prompt
    if request.style:
        full_prompt = f"{request.prompt}, in {request.style} style"

    try:
        adapter = await registry.get_adapter("image")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No image provider available: {e}")

    try:
        if hasattr(adapter, "generate_image"):
            url = await adapter.generate_image(prompt=full_prompt, model=request.model, size=request.size)
        else:
            url = f"https://image.pollinations.ai/prompt/{full_prompt.replace(' ', '%20')}"
        registry.report_success(adapter.provider_name)
        return {
            "data": [{"url": url}],
            "provider": adapter.provider_name,
            "prompt": full_prompt,
        }
    except Exception as e:
        registry.report_failure(adapter.provider_name, error=e)
        # Keyless fallback
        fallback_url = f"https://image.pollinations.ai/prompt/{full_prompt.replace(' ', '%20')}"
        return {
            "data": [{"url": fallback_url}],
            "provider": "pollinations_fallback",
            "prompt": full_prompt,
        }
