"""Asset schemas."""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict


class AssetBase(BaseModel):
    type: str = Field(..., pattern="^(image|video|audio|script|character|scene)$")
    name: str = Field(..., min_length=1, max_length=255)
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    model_id: Optional[str] = None
    style_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None


class AssetCreate(AssetBase):
    project_id: str
    metadata_json: Optional[dict[str, Any]] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None


class AssetRead(AssetBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
