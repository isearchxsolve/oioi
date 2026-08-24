"""
Pydantic schemas for API request/response validation.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Project Schemas ─────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    idea: str = Field("", max_length=5000)
    style: str = Field("cinematic, warm lighting, detailed", max_length=512)
    aspect: str = Field("16:9", pattern=r"^(16:9|9:16|1:1)$")
    voice: str = Field("aria")
    num_scenes: int = Field(6, ge=1, le=20)
    music: bool = False
    music_mood: str = Field("ambient", pattern=r"^(ambient|tense|bright)$")
    transition_mode: str = Field("cut", pattern=r"^(cut|crossfade)$")
    seed: Optional[int] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    idea: Optional[str] = None
    style: Optional[str] = None
    aspect: Optional[str] = None
    voice: Optional[str] = None
    num_scenes: Optional[int] = None
    music: Optional[bool] = None
    music_mood: Optional[str] = None
    transition_mode: Optional[str] = None
    seed: Optional[int] = None


class SceneUpdate(BaseModel):
    """Allow editing individual scene fields (narration, visual_prompt, cinematography, trim, transitions)."""
    narration: Optional[str] = None
    visual_prompt: Optional[str] = None
    shot_type: Optional[str] = None
    lens: Optional[str] = None
    lighting: Optional[str] = None
    camera_move: Optional[str] = None
    color_grade: Optional[str] = None
    trim_start_seconds: Optional[float] = None
    trim_end_seconds: Optional[float] = None
    transition_type: Optional[str] = None
    transition_duration: Optional[float] = None
    included: Optional[bool] = None
    character_id: Optional[str] = None


class SceneOut(BaseModel):
    id: str
    project_id: str
    index: int
    narration: str
    visual_prompt: str
    shot_type: Optional[str] = None
    lens: Optional[str] = None
    lighting: Optional[str] = None
    camera_move: Optional[str] = None
    color_grade: Optional[str] = None
    trim_start_seconds: Optional[float] = None
    trim_end_seconds: Optional[float] = None
    transition_type: Optional[str] = None
    transition_duration: Optional[float] = None
    included: bool = True
    character_id: Optional[str] = None
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    clip_path: Optional[str] = None
    duration: Optional[float] = None
    status: str
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: str
    name: str
    idea: str
    style: str
    aspect: str
    voice: str
    seed: int
    music: bool
    music_mood: str
    num_scenes: int
    transition_mode: str
    status: str
    output_path: Optional[str] = None
    srt_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    scenes: list[SceneOut] = []

    class Config:
        from_attributes = True


# ── Task Schemas ─────────────────────────────────────────────

class TaskOut(BaseModel):
    id: str
    project_id: str
    task_type: str
    status: str
    progress: float
    message: str
    result: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Pipeline Trigger Schemas ─────────────────────────────────

class GenerateScriptRequest(BaseModel):
    """Trigger script/storyboard generation."""
    num_scenes: int = Field(6, ge=1, le=20)


class GenerateVisualsRequest(BaseModel):
    """Trigger visual generation for all scenes (or specific scene indices)."""
    scene_indices: Optional[list[int]] = None  # None = all scenes


class GenerateAudioRequest(BaseModel):
    """Trigger narration synthesis for all scenes."""
    voice: Optional[str] = None  # None = use project default


class GenerateClipsRequest(BaseModel):
    """Trigger Ken Burns clip rendering for all scenes."""
    pass


class StitchRequest(BaseModel):
    """Trigger final film stitching."""
    mode: str = Field("cut", pattern=r"^(cut|crossfade)$")


class FullPipelineRequest(BaseModel):
    """Run the entire pipeline end-to-end."""
    num_scenes: int = Field(6, ge=1, le=20)
    mode: str = Field("cut", pattern=r"^(cut|crossfade)$")


# ── SSE Event Schemas ────────────────────────────────────────

class SSEEvent(BaseModel):
    event: str  # "progress", "scene_update", "completed", "error"
    data: dict[str, Any]


# ── Character Schemas ────────────────────────────────────────

class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=2000)


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CharacterOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str
    reference_image_path: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
