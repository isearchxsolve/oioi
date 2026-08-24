"""
SQLAlchemy ORM models for Film Kit Studio.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    SCRIPT_GENERATED = "script_generated"
    VISUALS_GENERATED = "visuals_generated"
    AUDIO_GENERATED = "audio_generated"
    CLIPS_GENERATED = "clips_generated"
    RENDERED = "rendered"
    ERROR = "error"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    idea: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[str] = mapped_column(String(512), default="cinematic, warm lighting, detailed")
    aspect: Mapped[str] = mapped_column(String(10), default="16:9")
    voice: Mapped[str] = mapped_column(String(50), default="aria")
    seed: Mapped[int] = mapped_column(Integer, default=42)
    music: Mapped[bool] = mapped_column(default=False)
    music_mood: Mapped[str] = mapped_column(String(20), default="ambient")
    num_scenes: Mapped[int] = mapped_column(Integer, default=6)
    transition_mode: Mapped[str] = mapped_column(String(20), default="cut")
    status: Mapped[str] = mapped_column(String(30), default=ProjectStatus.DRAFT.value)
    output_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    srt_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Scene.index"
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Character.created_at"
    )


class SceneStatus(str, enum.Enum):
    PENDING = "pending"
    SCRIPT_DONE = "script_done"
    VISUAL_PENDING = "visual_pending"
    VISUAL_DONE = "visual_done"
    AUDIO_PENDING = "audio_pending"
    AUDIO_DONE = "audio_done"
    CLIP_PENDING = "clip_pending"
    CLIP_DONE = "clip_done"
    ERROR = "error"


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    narration: Mapped[str] = mapped_column(Text, default="")
    visual_prompt: Mapped[str] = mapped_column(Text, default="")
    # ── Cinematography direction (nullable, additive) ───────
    # Populated by the upgraded script-generation prompt. Older
    # scenes/projects created before this field simply stay NULL.
    shot_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lens: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lighting: Mapped[str | None] = mapped_column(String(100), nullable=True)
    camera_move: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_grade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ── Review / trim / transition overrides (additive) ──────
    trim_in: Mapped[float | None] = mapped_column(Float, nullable=True)
    trim_out: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    included: Mapped[bool] = mapped_column(default=True)
    character_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=SceneStatus.PENDING.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="scenes")
    character: Mapped["Character"] = relationship(back_populates="scenes")


class Character(Base):
    """Character reference with optional reference image for visual consistency."""
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    reference_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    project: Mapped["Project"] = relationship(back_populates="characters")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="character")


class Task(Base):
    """Tracks long-running background tasks (pipeline steps)."""
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # "script", "visuals", "audio", "clips", "stitch", "full_pipeline"
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # "pending", "running", "completed", "failed"
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    # 0.0 → 1.0
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
