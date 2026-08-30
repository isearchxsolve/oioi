from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.provider_service import get_provider_registry
from app.api.v1.endpoints.legacy import require_legacy_demo_mode

router = APIRouter()


class AudioSpeechRequest(BaseModel):
    input: str
    voice: Optional[str] = "alloy"
    model: Optional[str] = "tts-1"


@router.post("/speech")
async def generate_speech(request: AudioSpeechRequest):
    """Generate audio speech for characters / narrator."""
    require_legacy_demo_mode()
    clean_text = request.input.replace(" ", "%20")
    audio_url = f"https://api.streamelements.com/kappa/v2/speech?voice=Brian&text={clean_text}"
    return {
        "status": "completed",
        "audio_url": audio_url,
        "voice": request.voice,
        "text": request.input,
    }
