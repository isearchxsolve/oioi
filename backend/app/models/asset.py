"""Asset ORM model.

An Asset is any generated or uploaded media artifact (image, video,
audio, script) belonging to a Project. Mirrors Alembic migration
`20260731_151203_create_asset_table`.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Text, JSON, Integer, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

class Asset(Base):
    """Generated or uploaded media asset with support for cinematic streaming metadata."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # image|video|audio|script|character|scene
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    hls_manifest_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    dash_manifest_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    poster_webp_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    aspect_ratio: Mapped[Optional[str]] = mapped_column(String(20), default="16:9", nullable=True)
    max_resolution: Mapped[Optional[str]] = mapped_column(String(20), default="1080p", nullable=True)
    cache_control_policy: Mapped[Optional[str]] = mapped_column(String(255), default="public, max-age=31536000, immutable", nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    style_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("styles.id"), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project", back_populates="assets")
    style = relationship("Style")

    def __repr__(self) -> str:
        return f"<Asset id={self.id} type={self.type!r} name={self.name!r}>"
