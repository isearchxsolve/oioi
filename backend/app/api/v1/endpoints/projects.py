from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import get_current_user
from app.core.database import get_session
from app.models.project import Project
from app.models.user import User

router = APIRouter()

class ProjectCreateRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    aspect_ratio: Optional[str] = "16:9"


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    canvas_state: Optional[Dict[str, Any]] = None


def _project_payload(project: Project) -> Dict[str, Any]:
    canvas = project.canvas_state or {"panels": [], "links": []}
    return {
        "id": project.id,
        "title": project.name,
        "description": project.description or "",
        "aspect_ratio": (project.settings or {}).get("aspect_ratio", "16:9"),
        "canvas_state": canvas,
        "created_at": project.created_at,
        "status": project.status,
    }


@router.post("/")
async def create_project(
    request: ProjectCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new AI animation film project."""
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id, user_id=user.id, name=request.title,
        description=request.description or None, status="draft",
        canvas_state={"panels": [], "links": []}, settings={"aspect_ratio": request.aspect_ratio},
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _project_payload(project)


@router.get("/")
async def list_projects(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    """List all user animation projects."""
    projects = list((await session.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
    )).all())
    return [_project_payload(project) for project in projects]


@router.get("/{project_id}")
async def get_project(
    project_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    """Get project details and canvas state."""
    project = await session.scalar(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _project_payload(project)


@router.put("/{project_id}")
async def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update project metadata or canvas state."""
    project = await session.scalar(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if request.title is not None:
        project.name = request.title
    if request.description is not None:
        project.description = request.description
    if request.canvas_state is not None:
        project.canvas_state = request.canvas_state
    await session.commit()
    await session.refresh(project)
    return _project_payload(project)
