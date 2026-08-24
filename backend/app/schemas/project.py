"""Project schemas."""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None


class ProjectCreate(ProjectBase):
    canvas_state: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|active|archived)$")
    thumbnail_url: Optional[str] = None
    canvas_state: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    status: str
    canvas_state: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
