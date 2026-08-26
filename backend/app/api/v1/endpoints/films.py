"""HTTP entrypoints for the durable film consumption pipeline.

These endpoints default to in-process mock video + mock chat.  Live mode is rejected
unless the caller supplies both safety switches; no endpoint can create an unbounded
live fan-out.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from film_pipeline.assembly import HttpClipMaterializer, SyntheticClipMaterializer
from film_pipeline.clients import ChatPoolClient, VideoRouterClient
from film_pipeline.mock import DeterministicMockChatClient, MockVideoBackend
from film_pipeline.orchestrator import FilmOrchestrator, FilmRequest
from film_pipeline.store import FilmJobStore

router = APIRouter()


class FilmCreateRequest(BaseModel):
    script: str = Field(min_length=1)
    target_seconds: int = Field(default=10_800, ge=5)
    aspect_ratio: str = "16:9"
    style: str = "cinematic"
    image_refs: list[str] = Field(default_factory=list)
    seed: Optional[int] = 20_260_826
    bible: Optional[Dict[str, Any]] = None
    admission_mode: Literal["refuse", "waves"] = "refuse"
    backend: Literal["mock", "live"] = "mock"
    live: bool = False
    max_clips: int = Field(default=0, ge=0)


class _ServicePool:
    def __init__(self) -> None:
        root = Path(os.getenv("FILM_PIPELINE_STORAGE_PATH", "./storage/film_pipeline")).resolve()
        self.root = root
        self.store = FilmJobStore(root / "film_jobs.sqlite3")
        self.mock_backend = MockVideoBackend()
        self._mock: Optional[FilmOrchestrator] = None
        self._live: Optional[FilmOrchestrator] = None

    def get(self, backend: str, *, max_clips: int = 0) -> FilmOrchestrator:
        if backend == "mock":
            if self._mock is None:
                video_http = httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=self.mock_backend.app), base_url="http://mock-video"
                )
                self._mock = FilmOrchestrator(
                    store=self.store, chat=DeterministicMockChatClient(),
                    video=VideoRouterClient(client=video_http), artifact_root=self.root / "artifacts",
                    materializer=SyntheticClipMaterializer(), segment_size=2,
                )
            return self._mock
        # A live instance is intentionally not cached: the per-invocation cap is part
        # of the authorization to spend and must not leak from an earlier request.
        return FilmOrchestrator(
            store=self.store,
            chat=ChatPoolClient(os.getenv("FILM_PIPELINE_CHAT_BASE_URL", "http://127.0.0.1:20130")),
            video=VideoRouterClient(
                os.getenv("FILM_PIPELINE_VIDEO_BASE_URL", "http://127.0.0.1:8189"),
                mode="live", live=True, max_clips=max_clips,
            ),
            artifact_root=self.root / "artifacts", materializer=HttpClipMaterializer(),
            execution_backend="live", live=True, max_clips=max_clips,
        )


_services = _ServicePool()


@router.post("/")
async def create_film(request: FilmCreateRequest):
    if request.backend == "live" and (not request.live or request.max_clips <= 0):
        raise HTTPException(
            status_code=400,
            detail="live generation requires both live=true and a positive max_clips safety cap",
        )
    orchestrator = _services.get(request.backend, max_clips=request.max_clips)
    try:
        return await orchestrator.request_film(FilmRequest(
            script=request.script, target_seconds=request.target_seconds, aspect_ratio=request.aspect_ratio,
            style=request.style, image_refs=request.image_refs, seed=request.seed, bible=request.bible,
            admission_mode=request.admission_mode,
            max_clips=request.max_clips if request.backend == "live" else None,
        ))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"film planning/admission failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if request.backend == "live":
            await orchestrator.aclose()


@router.get("/{film_id}")
async def get_film(film_id: str):
    try:
        return _services.store.summary(film_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{film_id}/tick")
async def tick_film(
    film_id: str,
    backend: Literal["mock", "live"] = "mock",
    live: bool = False,
    max_clips: int = 0,
):
    if backend == "live" and (not live or max_clips <= 0):
        raise HTTPException(status_code=400, detail="live scheduling requires live=true and a positive max_clips safety cap")
    orchestrator = _services.get(backend, max_clips=max_clips)
    try:
        return await orchestrator.tick(film_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"film scheduler tick failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if backend == "live":
            await orchestrator.aclose()
