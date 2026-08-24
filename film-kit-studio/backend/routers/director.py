"""
Director Router — API endpoints for autonomous filmmaking.
"""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from config import settings
from database import get_session
from models import Project
from services.director import (
    DirectorRun,
    DirectorRunStatus,
    DirectorLoop,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tasks.task_manager import task_manager

router = APIRouter(prefix="/api/director", tags=["director"])

logger = logging.getLogger(__name__)

# In-memory run store (in production, use Redis/DB)
_director_runs: dict[str, DirectorRun] = {}


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════

class DirectorRunRequest(BaseModel):
    """Request to start a new director run."""

    project_id: str = Field(..., description="Project ID to run director on")
    idea: str = Field(..., min_length=10, max_length=2000, description="Logline/idea for the film")
    genre: str = Field("drama", description="Film genre for planner context")
    target_duration: float = Field(60.0, ge=15, le=300, description="Target duration in seconds")
    max_iterations: int = Field(3, ge=1, le=10, description="Max critique/re-roll iterations")
    critic_threshold: float = Field(0.75, ge=0.5, le=1.0, description="Score threshold to pass")

class DirectorRunResponse(BaseModel):
    """Response with run ID and status."""

    run_id: str
    status: str
    message: str


# ═══════════════════════════════════════════════════════════════════════════
# SSE EVENT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

async def _director_event_generator(run_id: str):
    """Generate SSE events for a director run."""
    run = _director_runs.get(run_id)
    if not run:
        yield {"event": "error", "data": {"message": "Run not found"}}
        return

    # Initial event
    yield run.to_sse_event("started")

    # Poll for updates (in production, use async queue)
    last_iteration = -1
    while run.status in ("planning", "generating", "critiquing", "re_rolling"):
        await asyncio.sleep(1)

        # Emit update if iteration changed or new critique
        if run.current_iteration != last_iteration:
            last_iteration = run.current_iteration
            yield run.to_sse_event("iteration_update")

        # Check for new critique
        if run.critique_history and len(run.critique_history) > last_iteration:
            yield run.to_sse_event("critique_complete")

    # Final event
    if run.status == "completed":
        yield run.to_sse_event("completed")
    elif run.status == "failed":
        yield run.to_sse_event("error")


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/run", response_model=DirectorRunResponse)
async def start_director_run(
    request: DirectorRunRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Start a new autonomous director run.

    Returns a run_id immediately; connect to /events/{run_id} for SSE progress.
    """
    # Verify project exists
    stmt = select(Project).where(Project.id == request.project_id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create run
    run = DirectorRun(
        id=str(uuid.uuid4())[:8],
        project_id=request.project_id,
        idea=request.idea,
        genre=request.genre,
        target_duration=request.target_duration,
        max_iterations=request.max_iterations,
        critic_threshold=request.critic_threshold,
        status=DirectorRunStatus.PLANNING,
    )

    _director_runs[run.id] = run

    # Start background task
    async def run_director():
        loop = DirectorLoop(run)
        try:
            await loop.run_full_pipeline()
        except Exception as e:
            logger.exception(f"Director run {run.id} failed: {e}")
            run.status = DirectorRunStatus.FAILED
            run.error_message = str(e)

    background_tasks.add_task(run_director)

    return DirectorRunResponse(
        run_id=run.id,
        status=run.status,
        message="Director run started. Connect to /events/{run_id} for progress.",
    )


@router.get("/events/{run_id}")
async def director_events(run_id: str):
    """
    Server-Sent Events stream for director run progress.

    Event types: started, planning, generating_scene, scene_done, critiquing,
                 re_rolling, completed, error
    """
    if run_id not in _director_runs:
        raise HTTPException(status_code=404, detail="Run not found")

    return EventSourceResponse(_director_event_generator(run_id))


@router.get("/{run_id}/status")
async def director_status(run_id: str):
    """Get current status of a director run (polling fallback)."""
    run = _director_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "run_id": run.id,
        "status": run.status,
        "current_iteration": run.current_iteration,
        "max_iterations": run.max_iterations,
        "beats_count": len(run.plan.beats) if run.plan else 0,
        "scenes_count": len(run.plan.scene_specs) if run.plan else 0,
        "latest_score": run.critique_history[-1].overall_score if run.critique_history else 0,
        "latest_passed": run.critique_history[-1].passed if run.critique_history else False,
        "total_generations": run.total_generations,
        "total_re_rolls": run.total_re_rolls,
        "error_message": run.error_message,
        "final_outputs": {
            "edl": run.edl_path,
            "fcpxml": run.fcpxml_path,
            "premiere_xml": run.premiere_xml_path,
            "davinci_drt": run.davinci_drt_path,
            "prores_master": run.prores_master_path,
        } if run.status == "completed" else None,
    }


@router.get("/{run_id}/edl")
async def download_edl(run_id: str):
    """Download EDL (CMX 3600) file for the run."""
    from fastapi.responses import FileResponse

    run = _director_runs.get(run_id)
    if not run or not run.edl_path:
        raise HTTPException(status_code=404, detail="EDL not available")

    from pathlib import Path
    path = Path(run.edl_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="EDL file not found")

    return FileResponse(
        path=path,
        filename=f"director_{run_id}.edl",
        media_type="text/plain",
    )


@router.get("/{run_id}/fcpxml")
async def download_fcpxml(run_id: str):
    """Download FCPXML file for Final Cut Pro."""
    from fastapi.responses import FileResponse

    run = _director_runs.get(run_id)
    if not run or not run.fcpxml_path:
        raise HTTPException(status_code=404, detail="FCPXML not available")

    from pathlib import Path
    path = Path(run.fcpxml_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="FCPXML file not found")

    return FileResponse(
        path=path,
        filename=f"director_{run_id}.fcpxml",
        media_type="application/xml",
    )


@router.get("/{run_id}/premiere_xml")
async def download_premiere_xml(run_id: str):
    """Download Premiere Pro XML file."""
    from fastapi.responses import FileResponse

    run = _director_runs.get(run_id)
    if not run or not run.premiere_xml_path:
        raise HTTPException(status_code=404, detail="Premiere XML not available")

    from pathlib import Path
    path = Path(run.premiere_xml_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Premiere XML file not found")

    return FileResponse(
        path=path,
        filename=f"director_{run_id}.xml",
        media_type="application/xml",
    )


@router.get("/{run_id}/davinci_drt")
async def download_davinci_drt(run_id: str):
    """Download DaVinci Resolve DRT file."""
    from fastapi.responses import FileResponse

    run = _director_runs.get(run_id)
    if not run or not run.davinci_drt_path:
        raise HTTPException(status_code=404, detail="DaVinci DRT not available")

    from pathlib import Path
    path = Path(run.davinci_drt_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="DaVinci DRT file not found")

    return FileResponse(
        path=path,
        filename=f"director_{run_id}.drt",
        media_type="application/xml",
    )


@router.get("/{run_id}/report")
async def director_report(run_id: str):
    """Get detailed report of a director run."""
    run = _director_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "idea": run.idea,
        "genre": run.genre,
        "target_duration": run.target_duration,
        "status": run.status,
        "iterations": run.current_iteration + 1,
        "max_iterations": run.max_iterations,
        "critic_threshold": run.critic_threshold,
        "plan": run.plan.dict() if run.plan else None,
        "critique_history": [c.dict() for c in run.critique_history],
        "continuity_report": run.continuity_state.get_consistency_report() if hasattr(run.continuity_state, 'get_consistency_report') else {},
        "final_outputs": {
            "edl": run.edl_path,
            "fcpxml": run.fcpxml_path,
            "premiere_xml": run.premiere_xml_path,
            "davinci_drt": run.davinci_drt_path,
            "prores_master": run.prores_master_path,
        },
        "stats": {
            "total_generations": run.total_generations,
            "total_re_rolls": run.total_re_rolls,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        },
        "error_message": run.error_message,
    }


@router.delete("/{run_id}")
async def cancel_director_run(run_id: str):
    """Cancel a running director job."""
    run = _director_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Run already finished")

    run.status = DirectorRunStatus.FAILED
    run.error_message = "Cancelled by user"

    return {"message": "Run cancelled", "run_id": run_id}


@router.get("")
async def list_director_runs(project_id: Optional[str] = Query(None)):
    """List all director runs, optionally filtered by project."""
    runs = _director_runs.values()
    if project_id:
        runs = [r for r in runs if r.project_id == project_id]

    return [
        {
            "run_id": r.id,
            "project_id": r.project_id,
            "idea": r.idea[:100],
            "genre": r.genre,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in sorted(runs, key=lambda x: x.created_at, reverse=True)
    ]