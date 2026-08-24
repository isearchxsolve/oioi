"""
Pipeline router — triggers and monitors long-running generation tasks.

Endpoints:
  POST /api/pipeline/{project_id}/script       — Generate script/storyboard
  POST /api/pipeline/{project_id}/visuals      — Generate visuals (Cosmos3)
  POST /api/pipeline/{project_id}/audio        — Generate narration (edge-tts)
  POST /api/pipeline/{project_id}/clips        — Render clips (FFMPEG)
  POST /api/pipeline/{project_id}/stitch       — Stitch final film
  POST /api/pipeline/{project_id}/full        — Run entire pipeline
  GET  /api/pipeline/tasks/{task_id}           — Poll task status
  GET  /api/pipeline/tasks/{task_id}/events    — SSE stream for task
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from database import get_session
from models import Task
from schemas import (
    FullPipelineRequest,
    GenerateAudioRequest,
    GenerateClipsRequest,
    GenerateScriptRequest,
    GenerateVisualsRequest,
    StitchRequest,
    TaskOut,
)
from services.pipeline import (
    run_audio_generation,
    run_clip_generation,
    run_full_pipeline,
    run_script_generation,
    run_stitching,
    run_visual_generation,
)
from tasks.task_manager import task_manager

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


# ── Task triggers ───────────────────────────────────────────

@router.post("/{project_id}/script", response_model=TaskOut)
async def trigger_script(
    project_id: str,
    data: GenerateScriptRequest,
    session: AsyncSession = Depends(get_session),
):
    """Trigger script/storyboard generation via NIM LLM."""
    # Verify project exists
    from models import Project
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = await task_manager.create_task(project_id, "script")
    await task_manager.start_task(
        task_id,
        run_script_generation(task_id, project_id, data.num_scenes),
    )

    # Return task info
    task = await task_manager.get_task(task_id)
    return task


@router.post("/{project_id}/visuals", response_model=TaskOut)
async def trigger_visuals(
    project_id: str,
    data: GenerateVisualsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Trigger visual generation via NVIDIA Cosmos3 NIM."""
    from models import Project
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = await task_manager.create_task(project_id, "visuals")
    await task_manager.start_task(
        task_id,
        run_visual_generation(task_id, project_id, data.scene_indices),
    )

    task = await task_manager.get_task(task_id)
    return task


@router.post("/{project_id}/audio", response_model=TaskOut)
async def trigger_audio(
    project_id: str,
    data: GenerateAudioRequest,
    session: AsyncSession = Depends(get_session),
):
    """Trigger narration synthesis via edge-tts."""
    from models import Project
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = await task_manager.create_task(project_id, "audio")
    await task_manager.start_task(
        task_id,
        run_audio_generation(task_id, project_id, data.voice),
    )

    task = await task_manager.get_task(task_id)
    return task


@router.post("/{project_id}/clips", response_model=TaskOut)
async def trigger_clips(
    project_id: str,
    data: GenerateClipsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Trigger Ken Burns clip rendering via FFMPEG."""
    from models import Project
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = await task_manager.create_task(project_id, "clips")
    await task_manager.start_task(
        task_id,
        run_clip_generation(task_id, project_id),
    )

    task = await task_manager.get_task(task_id)
    return task


@router.post("/{project_id}/stitch", response_model=TaskOut)
async def trigger_stitch(
    project_id: str,
    data: StitchRequest,
    session: AsyncSession = Depends(get_session),
):
    """Trigger final film stitching via FFMPEG."""
    from models import Project
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = await task_manager.create_task(project_id, "stitch")
    await task_manager.start_task(
        task_id,
        run_stitching(task_id, project_id, data.mode),
    )

    task = await task_manager.get_task(task_id)
    return task


@router.post("/{project_id}/full", response_model=TaskOut)
async def trigger_full_pipeline(
    project_id: str,
    data: FullPipelineRequest,
    session: AsyncSession = Depends(get_session),
):
    """Run the entire pipeline end-to-end."""
    from models import Project
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = await task_manager.create_task(project_id, "full_pipeline")
    await task_manager.start_task(
        task_id,
        run_full_pipeline(task_id, project_id, data.num_scenes, data.mode),
    )

    task = await task_manager.get_task(task_id)
    return task


# ── Task monitoring ─────────────────────────────────────────

@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task_status(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Poll task status (for clients not using SSE)."""
    task = await task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/events")
async def task_sse_stream(task_id: str):
    """
    Server-Sent Events stream for real-time task progress.

    The frontend can connect to this endpoint to receive:
      - progress events (overall progress + message)
      - scene_update events (per-scene status changes)
      - completed event (final result)
      - error event (failure details)
    """
    async def event_generator():
        async for event in task_manager.get_sse_stream(task_id):
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(event_generator())
