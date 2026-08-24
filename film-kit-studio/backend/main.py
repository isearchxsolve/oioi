"""
Film Kit Studio — FastAPI Backend Entry Point

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from routers import characters, director, media, pipeline, projects, training

# ── Logging ─────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("film_kit_studio")


# ── Lifespan ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Film Kit Studio backend starting up...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Film Kit Studio backend shutting down...")


# ── App ─────────────────────────────────────────────────────

app = FastAPI(
    title="Film Kit Studio API",
    description="Browser-based AI filmmaking platform — backend for script generation, visual synthesis, narration, and FFMPEG video assembly.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────

app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(media.router)
app.include_router(characters.router)
app.include_router(director.router)
app.include_router(training.router)


# ── Health Check ────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "Film Kit Studio API",
        "version": "1.0.0",
        "ffmpeg_available": _check_ffmpeg(),
    }


def _check_ffmpeg() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# ── Constants endpoint (for frontend) ───────────────────────

@app.get("/api/constants")
async def get_constants():
    """Return static constants (voices, styles, aspects) for the frontend."""
    from config import ASPECTS, MUSIC_MOODS, VOICES, VISUAL_STYLES

    return {
        "aspects": ASPECTS,
        "voices": VOICES,
        "music_moods": MUSIC_MOODS,
        "visual_styles": VISUAL_STYLES,
        "providers": {
            "visual": ["cosmos", "veo", "kling"],
            "voice": ["edge", "elevenlabs"],
            "music": ["ffmpeg", "suno"],
            "script": ["nim", "openai", "anthropic", "gemini"],
        },
    }