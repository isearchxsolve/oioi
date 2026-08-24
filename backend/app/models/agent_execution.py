"""AgentExecution ORM model.

An AgentExecution records a single run of one of the 7 specialized AI
agents in the OiiOii.ai animation pipeline (Scriptwriter, Art Director,
Character Designer, Scene Designer, Animator, Sound Director, Director).
Mirrors Alembic migration `20260731_151206_create_agent_execution_table`.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Text, JSON, Integer, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AgentExecution(Base):
    """A single AI agent run within a project pipeline."""

    __tablename__ = "agent_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # scriptwriter|art_director|character_designer|scene_designer|animator|sound_director|director
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending|running|completed|failed
    input_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="agent_executions")

    def __repr__(self) -> str:
        return f"<AgentExecution id={self.id} agent={self.agent_type!r} status={self.status!r}>"
