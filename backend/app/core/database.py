from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


# Engine is created lazily so importing this module does not require a live DB.
engine = None
async_session_maker = None
_schema_initialized = False


def _init_engine():
    """Create the async engine + session maker on first use."""
    global engine, async_session_maker
    if engine is None:
        db_url = settings.DATABASE_URL
        if db_url and db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://")
        if not db_url or "crypto_db" in db_url:
            db_url = "sqlite+aiosqlite:///./test.db"
        engine = create_async_engine(db_url, echo=settings.DEBUG)
        async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, async_session_maker


async def init_db():
    global _schema_initialized
    # Import the model package before metadata creation.  Several legacy routes
    # used only in-memory state, so no model import previously happened during
    # startup and a fresh deployment could start without the users table.
    import app.models  # noqa: F401

    _, session_maker = _init_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _schema_initialized = True


async def get_session() -> AsyncSession:
    # TestClient instances used outside a lifespan context and small scripts still
    # receive a usable database. Production performs this during lifespan startup.
    if not _schema_initialized:
        await init_db()
    _, session_maker = _init_engine()
    async with session_maker() as session:
        yield session
