"""Style ORM model.

A Style is one of the 150+ built-in visual styles offered by OiiOii.ai
(anime, realistic, 3D, pixel art, painting, illustration, etc.).
Mirrors Alembic migration `20260731_151204_create_style_table`.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Style(Base):
    """Built-in or custom visual style."""

    __tablename__ = "styles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # anime|realistic|3d|pixel|painting|illustration
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    prompt_suffix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # appended to generation prompts
    negative_prompt_suffix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Style id={self.id} name={self.name!r} category={self.category!r}>"
