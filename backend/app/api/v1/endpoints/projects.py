from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import datetime

router = APIRouter()

# In-memory storage for projects and canvas state
_PROJECTS_DB: Dict[str, Dict[str, Any]] = {}


class ProjectCreateRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    aspect_ratio: Optional[str] = "16:9"


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    canvas_state: Optional[Dict[str, Any]] = None


@router.post("/")
async def create_project(request: ProjectCreateRequest):
    """Create a new AI animation film project."""
    project_id = str(uuid.uuid4())
    project = {
        "id": project_id,
        "title": request.title,
        "description": request.description,
        "aspect_ratio": request.aspect_ratio,
        "canvas_state": {"panels": [], "links": []},
        "created_at": datetime.datetime.utcnow().isoformat(),
        "status": "draft",
    }
    _PROJECTS_DB[project_id] = project
    return project


@router.get("/")
async def list_projects():
    """List all user animation projects."""
    return list(_PROJECTS_DB.values())


@router.get("/{project_id}")
async def get_project(project_id: str):
    """Get project details and canvas state."""
    if project_id not in _PROJECTS_DB:
        # Mock default project for seamless experience
        return {
            "id": project_id,
            "title": "Default Project",
            "description": "Auto-generated workspace",
            "aspect_ratio": "16:9",
            "canvas_state": {"panels": [], "links": []},
            "status": "active",
        }
    return _PROJECTS_DB[project_id]


@router.put("/{project_id}")
async def update_project(project_id: str, request: ProjectUpdateRequest):
    """Update project metadata or canvas state."""
    if project_id not in _PROJECTS_DB:
        _PROJECTS_DB[project_id] = {
            "id": project_id,
            "title": request.title or "Project",
            "description": request.description or "",
            "canvas_state": request.canvas_state or {},
            "status": "active",
        }
    else:
        if request.title:
            _PROJECTS_DB[project_id]["title"] = request.title
        if request.description:
            _PROJECTS_DB[project_id]["description"] = request.description
        if request.canvas_state:
            _PROJECTS_DB[project_id]["canvas_state"] = request.canvas_state
    return _PROJECTS_DB[project_id]
