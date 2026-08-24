"""
Characters router — CRUD for character references with image upload.

Provides:
  GET    /api/projects/{project_id}/characters           — list characters
  POST   /api/projects/{project_id}/characters           — create character
  GET    /api/projects/{project_id}/characters/{char_id} — get character
  PATCH  /api/projects/{project_id}/characters/{char_id} — update character
  POST   /api/projects/{project_id}/characters/{char_id}/image — upload reference image (multipart)
  DELETE /api/projects/{project_id}/characters/{char_id} — delete character

Reference images are saved to projects/{project_id}/images/char_{char_id}.{ext}
and served by the existing media router at /api/media/image/{project_id}/{filename}.
"""

import os
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_session
from models import Character, Project
from schemas import CharacterCreate, CharacterOut, CharacterUpdate

router = APIRouter(prefix="/api/projects/{project_id}/characters", tags=["characters"])


async def _get_project(session: AsyncSession, project_id: str) -> Project:
    """Load project or raise 404."""
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=List[CharacterOut])
async def list_characters(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List all characters for a project."""
    await _get_project(session, project_id)
    stmt = select(Character).where(Character.project_id == project_id).order_by(Character.created_at)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=CharacterOut, status_code=status.HTTP_201_CREATED)
async def create_character(
    project_id: str,
    payload: CharacterCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new character reference."""
    await _get_project(session, project_id)
    
    character = Character(
        id=str(uuid.uuid4()),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(character)
    await session.commit()
    await session.refresh(character)
    return character


@router.get("/{char_id}", response_model=CharacterOut)
async def get_character(
    project_id: str,
    char_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a single character by ID."""
    await _get_project(session, project_id)
    stmt = select(Character).where(Character.id == char_id, Character.project_id == project_id)
    result = await session.execute(stmt)
    character = result.scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.patch("/{char_id}", response_model=CharacterOut)
async def update_character(
    project_id: str,
    char_id: str,
    payload: CharacterUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update character name/description."""
    await _get_project(session, project_id)
    stmt = select(Character).where(Character.id == char_id, Character.project_id == project_id)
    result = await session.execute(stmt)
    character = result.scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")

    if payload.name is not None:
        character.name = payload.name
    if payload.description is not None:
        character.description = payload.description

    await session.commit()
    await session.refresh(character)
    return character


@router.post("/{char_id}/image", response_model=CharacterOut)
async def upload_character_image(
    project_id: str,
    char_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload a reference image for a character (multipart/form-data)."""
    await _get_project(session, project_id)
    stmt = select(Character).where(Character.id == char_id, Character.project_id == project_id)
    result = await session.execute(stmt)
    character = result.scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")

    # Validate file type
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Determine extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"  # default

    # Save to projects/{id}/images/char_{char_id}.{ext}
    images_dir = settings.projects_path / project_id / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"char_{char_id}{ext}"
    file_path = images_dir / filename
    
    # Delete old reference image if exists
    if character.reference_image_path:
        old_path = settings.projects_path / project_id / "images" / Path(character.reference_image_path).name
        old_path.unlink(missing_ok=True)

    # Write new file
    content = await file.read()
    file_path.write_bytes(content)

    # Update character with relative path
    character.reference_image_path = f"images/{filename}"
    await session.commit()
    await session.refresh(character)
    
    return character


@router.delete("/{char_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(
    project_id: str,
    char_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a character and its reference image."""
    await _get_project(session, project_id)
    stmt = select(Character).where(Character.id == char_id, Character.project_id == project_id)
    result = await session.execute(stmt)
    character = result.scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")

    # Delete reference image file
    if character.reference_image_path:
        img_path = settings.projects_path / project_id / character.reference_image_path
        img_path.unlink(missing_ok=True)

    await session.delete(character)
    await session.commit()