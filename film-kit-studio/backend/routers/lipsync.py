"""
Lip-Sync Router — API endpoints for face animation.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from config import settings
from database import get_session
from models import Character, Project, Scene
from services.face_animation import run_lip_sync
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/lipsync", tags=["lipsync"])

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ════════════════════════════════════════════════════════════════════════════

class LipSyncRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    character_id: str = Field(..., description="Character ID (must have reference image)")
    scene_id: str = Field(..., description="Scene ID to lip-sync")
    method: str = Field("liveportrait", description="liveportrait | sadtalker")
    fps: int = Field(30, ge=15, le=60)


class LipSyncResponse(BaseModel):
    job_id: str
    status: str
    message: str


class LipSyncStatus(BaseModel):
    job_id: str
    status: str  # pending | running | completed | failed
    progress: float
    message: str
    output_path: Optional[str] = None
    error: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# IN-MEMORY JOB STORE
# ════════════════════════════════════════════════════════════════════════════

_lipsync_jobs: dict[str, dict] = {}


# ════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@router.post("/generate", response_model=LipSyncResponse)
async def generate_lip_sync(
    request: LipSyncRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = get_session,
):
    """Generate lip-synced video for a scene."""
    from config import settings
    from sqlalchemy import select

    # Verify project
    from models import Project
    stmt = select(Project).where(Project.id == request.project_id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify character
    from models import Character
    stmt = select(Character).where(Character.id == request.character_id, Character.project_id == request.project_id)
    result = await session.execute(stmt)
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if not character.reference_image_path:
        raise HTTPException(status_code=400, detail="Character has no reference image")

    # Verify scene
    from models import Scene
    stmt = select(Scene).where(Scene.id == request.scene_id, Scene.project_id == request.project_id)
    result = await session.execute(stmt)
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    if not scene.audio_path:
        raise HTTPException(status_code=400, detail="Scene has no audio track")

    # Create job
    import uuid
    job_id = f"lipsync_{uuid.uuid4().hex[:8]}"
    _lipsync_jobs[job_id] = {
        "job_id": job_id,
        "project_id": request.project_id,
        "character_id": request.character_id,
        "scene_id": request.scene_id,
        "method": request.method,
        "fps": request.fps,
        "status": "pending",
        "progress": 0.0,
        "message": "Queued",
        "output_path": None,
        "error": None,
    }

    # Start background task
    background_tasks.add_task(_run_lip_sync_job, job_id)

    return LipSyncResponse(
        job_id=job_id,
        status="pending",
        message="Lip-sync job queued",
    )


@router.get("/{job_id}/status", response_model=LipSyncStatus)
async def get_lip_sync_status(job_id: str):
    """Get lip-sync job status."""
    job = _lipsync_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return LipSyncStatus(**job)


@router.get("/{job_id}/result")
async def get_lip_sync_result(job_id: str):
    """Download the lip-synced video."""
    from fastapi.responses import FileResponse

    job = _lipsync_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    if not job["output_path"]:
        raise HTTPException(status_code=404, detail="No output file")

    path = Path(job["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        path=path,
        filename=f"lipsync_{job_id}.mp4",
        media_type="video/mp4",
    )


@router.get("/scene/{scene_id}/history")
async def get_scene_lip_sync_history(
    scene_id: str,
    session: AsyncSession = get_session,
):
    """Get all lip-sync jobs for a scene."""
    from models import Scene
    stmt = select(Scene).where(Scene.id == scene_id)
    result = await session.execute(stmt)
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    jobs = [
        j for j in _lipsync_jobs.values()
        if j["scene_id"] == scene_id
    ]

    return sorted(jobs, key=lambda x: x.get("created_at", ""), reverse=True)


# ════════════════════════════════════════════════════════════════════════════
# BACKGROUND TASK
# ════════════════════════════════════════════════════════════════════════════

async def _run_lip_sync_job(job_id: str):
    """Background task to run lip-sync generation."""
    job = _lipsync_jobs.get(job_id)
    if not job:
        return

    from database import async_session
    from config import settings

    async with async_session() as session:
        try:
            job["status"] = "running"
            job["message"] = "Loading assets..."

            # Load assets
            from models import Character, Scene
            stmt = select(Character).where(Character.id == job["character_id"])
            result = await session.execute(stmt)
            character = result.scalar_one()

            stmt = select(Scene).where(Scene.id == job["scene_id"])
            result = await session.execute(stmt)
            scene = result.scalar_one()

            # Paths
            character_image = settings.projects_path / character.reference_image_path
            audio_path = settings.projects_path / scene.audio_path
            output_dir = settings.projects_path / job["project_id"] / "lipsync"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"scene_{scene.index:03d}_lipsync.mp4"

            # Run lip-sync
            from services.face_animation import run_lip_sync

            job["progress"] = 0.3
            job["message"] = "Running lip-sync..."

            output = await run_lip_sync(
                character_image=character_image,
                audio_path=audio_path,
                output_path=output_path,
                method=job["method"],
                fps=job["fps"],
            )

            job["status"] = "completed"
            job["progress"] = 1.0
            job["message"] = "Lip-sync completed"
            job["output_path"] = str(output_path)

        except Exception as e:
            logger.exception(f"Lip-sync job {job_id} failed: {e}")
            job["status"] = "failed"
            job["error"] = str(e)
            job["message"] = f"Failed: {e}"