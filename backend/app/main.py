import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core import database as db
from app.services.auth_service import OwnerBootstrapError, bootstrap_owner
from app.services.provider_service import init_registry, shutdown_registry, get_provider_registry
from app.api.v1.api import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure schema exists and providers are registered.
    await db.init_db()
    _, session_maker = db._init_engine()
    async with session_maker() as session:
        try:
            await bootstrap_owner(session)
        except OwnerBootstrapError:
            # An owner-less production server must never expose protected workspaces.
            # In development the operator may configure the owner later; login remains
            # impossible until one exists.
            if settings.APP_ENV.lower() in {"production", "prod"}:
                raise
    os.makedirs(settings.STORAGE_PATH, exist_ok=True)
    await init_registry()
    yield
    # Shutdown
    await shutdown_registry()

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="OiiOii.ai Studio - AI-powered animation agent platform using multi-provider free-tier adapters",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    lifespan=lifespan,
)

# Rate limiter registration
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Generated artifacts are intentionally not mounted as a public static tree.
# Customer-visible media is served only by ownership-checked API endpoints
# (for example /api/v1/films/{id}/artifact and /api/v1/assets/*).

@app.get("/health")
@app.get("/healthz", include_in_schema=False)
async def health_check():
    """Health check endpoint — queries the multi-provider registry snapshot."""
    registry = await get_provider_registry()
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "providers": registry.snapshot(),
    }

@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": f"{settings.API_V1_PREFIX}/docs",
    }

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
