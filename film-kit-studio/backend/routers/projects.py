"""
Projects router — CRUD operations for film projects.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_session
from models import Project, Scene
from schemas import ProjectCreate, ProjectOut, ProjectUpdate, SceneOut, SceneUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=List[ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_session)):
    """List all projects, newest first."""
    stmt = (
        select(Project)
        .options(selectinload(Project.scenes))
        .order_by(Project.created_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().unique().all()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new project."""
    import random

    project = Project(
        id=str(uuid.uuid4()),
        name=data.name,
        idea=data.idea,
        style=data.style,
        aspect=data.aspect,
        voice=data.voice,
        seed=data.seed if data.seed is not None else random.randint(0, 999_999),
        music=data.music,
        music_mood=data.music_mood,
        num_scenes=data.num_scenes,
        transition_mode=data.transition_mode,
        status="draft",
    )
    session.add(project)
    await session.commit()
    # Eagerly load the (empty) scenes relationship so the response model
    # doesn't attempt synchronous lazy-loading — which fails in async
    # context (MissingGreenlet).
    await session.refresh(project, ["scenes"])
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a single project with all its scenes."""
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.scenes))
    )
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update project fields."""
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.scenes))
    )
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a project and all its scenes."""
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Also delete project files
    from config import settings
    import shutil
    proj_dir = settings.projects_path / project_id
    if proj_dir.exists():
        shutil.rmtree(proj_dir, ignore_errors=True)

    await session.delete(project)
    await session.commit()


@router.patch("/{project_id}/scenes/{scene_id}", response_model=SceneOut)
async def update_scene(
    project_id: str,
    scene_id: str,
    data: SceneUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a single scene's narration or visual_prompt (editable storyboard)."""
    stmt = select(Scene).where(Scene.id == scene_id, Scene.project_id == project_id)
    result = await session.execute(stmt)
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(scene, key, value)

    await session.commit()
    await session.refresh(scene)
    return scene


@router.post("/{project_id}/scenes/reorder", response_model=List[SceneOut])
async def reorder_scenes(
    project_id: str,
    scene_ids: List[str],
    session: AsyncSession = Depends(get_session),
):
    """Reorder scenes by providing an ordered list of scene IDs."""
    stmt = select(Scene).where(Scene.project_id == project_id)
    result = await session.execute(stmt)
    scenes = {s.id: s for s in result.scalars()}

    for new_index, scene_id in enumerate(scene_ids):
        if scene_id in scenes:
            scenes[scene_id].index = new_index

    await session.commit()

    # Return updated scenes in order
    stmt = (
        select(Scene)
        .where(Scene.project_id == project_id)
        .order_by(Scene.index)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
