"""Style schemas."""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict


class StyleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., pattern="^(anime|realistic|3d|pixel|painting|illustration|other)$")
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    prompt_suffix: Optional[str] = None
    negative_prompt_suffix: Optional[str] = None


class StyleCreate(StyleBase):
    is_builtin: bool = False
    metadata_json: Optional[dict[str, Any]] = None


class StyleRead(StyleBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_builtin: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
