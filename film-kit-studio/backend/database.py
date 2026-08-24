"""
Database engine and session management.
Uses SQLAlchemy 2.0 async with aiosqlite for SQLite.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _migrate_sqlite_columns() -> None:
    """
    Idempotent column additions for existing SQLite databases.
    SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS, so we
    try each ADD COLUMN and silently ignore "duplicate column" errors.
    Runs on startup after create_all (which creates new tables but doesn't
    add missing columns to existing tables).
    """
    if not settings.database_url.startswith("sqlite"):
        return  # only needed for SQLite; Postgres etc. need Alembic

    columns_to_add = [
        # scenes table
        ("scenes", "trim_start_seconds", "REAL DEFAULT 0.5"),
        ("scenes", "trim_end_seconds", "REAL DEFAULT 0.5"),
        ("scenes", "transition_type", "VARCHAR(20) DEFAULT 'crossfade'"),
        ("scenes", "transition_duration", "REAL DEFAULT 0.5"),
        ("scenes", "included", "BOOLEAN DEFAULT 1"),
        ("scenes", "character_id", "VARCHAR(36) REFERENCES characters(id) ON DELETE SET NULL"),
    ]

    async with engine.begin() as conn:
        for table, column, col_def in columns_to_add:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
            except Exception:
                # SQLite raises OperationalError on duplicate column; ignore
                pass


async def init_db() -> None:
    """Create all tables. Called on application startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Run idempotent column migrations for existing SQLite DBs
    await _migrate_sqlite_columns()


async def get_session() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with async_session() as session:
        yield session
