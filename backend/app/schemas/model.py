"""Model schemas."""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict


class ModelBase(BaseModel):
    id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., pattern="^(llm|image|video|audio|embedding|vision|code|other)$")
    provider: str = "nvidia"
    description: Optional[str] = None
    capabilities: Optional[list[str]] = None


class ModelCreate(ModelBase):
    is_active: bool = True
    metadata_json: Optional[dict[str, Any]] = None


class ModelRead(ModelBase):
    model_config = ConfigDict(from_attributes=True)
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
