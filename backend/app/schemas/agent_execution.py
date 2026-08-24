"""AgentExecution schemas."""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict


_AGENT_TYPES = (
    "scriptwriter|art_director|character_designer|scene_designer|"
    "animator|sound_director|director"
)
_STATUS = "^(pending|running|completed|failed)$"


class AgentExecutionBase(BaseModel):
    agent_type: str = Field(..., pattern=f"^({_AGENT_TYPES})$")
    model_id: Optional[str] = None
    prompt: Optional[str] = None


class AgentExecutionCreate(AgentExecutionBase):
    project_id: str
    input_data: Optional[dict[str, Any]] = None


class AgentExecutionUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern=_STATUS)
    output_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None


class AgentExecutionRead(AgentExecutionBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    status: str
    input_data: Optional[dict[str, Any]] = None
    output_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
