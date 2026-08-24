"""Model ORM model.

A Model record represents a NVIDIA NIM model registered with the platform
(25+ image/video models). Cached metadata from the NIM `/models` endpoint
is stored here for fast UI population. Mirrors Alembic migration
`20260731_151205_create_model_table`.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Model(Base):
    """Registered NVIDIA NIM model metadata."""

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # e.g. nvidia/nemotron-3-ultra
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # llm|image|video|audio|embedding|vision
    provider: Mapped[str] = mapped_column(String(100), default="nvidia", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capabilities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # ["chat","completion"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Model id={self.id} name={self.name!r} category={self.category!r}>"
