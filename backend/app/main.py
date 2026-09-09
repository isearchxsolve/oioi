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
from app.api.v1.api import api_router
from film_pipeline.clients import ChatPoolClient

CANONICAL_CONSUMER_BASE_URL = "http://127.0.0.1:8190/v1"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure schema exists. Provider adapters are not initialized in
    # the web process; all billable inference belongs to the canonical consumer
    # gateway and is opened per request by the durable film/chat clients.
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
    yield

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

@app.get("/healthz", include_in_schema=False)
async def liveness_check():
    """Constant-time process liveness; never depends on consumer auth or upstreams.

    The Session Pool Shim deliberately protects ``/v1/models`` when its tenant map
    is present.  Using that authenticated readiness surface for ``/healthz`` made a
    healthy OiiOii process look dead whenever this app had not been given a tenant
    bearer.  Readiness is exposed separately at ``/health`` and
    ``/api/v1/providers/health``; this watchdog endpoint only answers whether this
    FastAPI process is alive.
    """

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "transport": CANONICAL_CONSUMER_BASE_URL,
        "providers": [],
        "catalogue_only": True,
        "consumer_catalogue": "not_probed",
    }


@app.get("/health")
async def health_check():
    """Non-spending readiness check against the authenticated consumer catalogue."""
    client = None
    try:
        client = ChatPoolClient()
        catalogue = await client.models()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "app": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "transport": CANONICAL_CONSUMER_BASE_URL,
                "error": f"canonical catalogue unavailable: {type(exc).__name__}",
            },
        )
    finally:
        if client is not None:
            await client.aclose()
    rows = catalogue.get("data") or []
    routes = sorted({
        str(row.get("id"))
        for row in rows
        if isinstance(row, dict) and str(row.get("id") or "").startswith(("video/", "session-pool/"))
    })
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "transport": CANONICAL_CONSUMER_BASE_URL,
        "providers": routes,
        "catalogue_only": True,
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
