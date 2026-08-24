"""
Media router — serves generated media files (videos, images, audio, SRT).
"""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import settings

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/video/{project_id}/{filename}")
async def serve_video(project_id: str, filename: str):
    """Serve a video file from a project's output directory."""
    safe_filename = Path(filename).name  # prevent path traversal
    file_path = settings.projects_path / project_id / "output" / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=safe_filename,
    )


@router.get("/image/{project_id}/{filename}")
async def serve_image(project_id: str, filename: str):
    """Serve an image file from a project's images directory."""
    safe_filename = Path(filename).name
    file_path = settings.projects_path / project_id / "images" / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    mime, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        media_type=mime or "image/jpeg",
        filename=safe_filename,
    )


@router.get("/clip/{project_id}/{filename}")
async def serve_clip(project_id: str, filename: str):
    """Serve a clip file from a project's clips directory."""
    safe_filename = Path(filename).name
    file_path = settings.projects_path / project_id / "clips" / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=safe_filename,
    )


@router.get("/srt/{project_id}/{filename}")
async def serve_srt(project_id: str, filename: str):
    """Serve an SRT subtitle file."""
    safe_filename = Path(filename).name
    file_path = settings.projects_path / project_id / "output" / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Subtitle file not found")
    return FileResponse(
        path=str(file_path),
        media_type="text/plain",
        filename=safe_filename,
    )
