"""Pydantic schemas for request/response validation.

This package groups all API schemas (DTOs) used by the FastAPI endpoints.
Importing it registers the schema modules with the package namespace.
"""

from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate
from app.schemas.style import StyleRead, StyleCreate
from app.schemas.model import ModelRead, ModelCreate
from app.schemas.agent_execution import (
    AgentExecutionCreate,
    AgentExecutionRead,
    AgentExecutionUpdate,
)

__all__ = [
    "UserCreate", "UserRead", "UserUpdate",
    "ProjectCreate", "ProjectRead", "ProjectUpdate",
    "AssetCreate", "AssetRead", "AssetUpdate",
    "StyleRead", "StyleCreate",
    "ModelRead", "ModelCreate",
    "AgentExecutionCreate", "AgentExecutionRead", "AgentExecutionUpdate",
]
