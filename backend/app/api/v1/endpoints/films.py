"""HTTP entrypoints for the durable film consumption pipeline.

These endpoints default to in-process mock video + mock chat.  Live mode is rejected
unless the caller supplies both safety switches; no endpoint can create an unbounded
live fan-out.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from film_pipeline.assembly import HttpClipMaterializer, SyntheticClipMaterializer
from film_pipeline.clients import ChatPoolClient, VideoRouterClient
from film_pipeline.crew import CrewHandoffError, admit_approved_crew_film
from film_pipeline.mock import DeterministicMockChatClient, MockVideoBackend
from film_pipeline.orchestrator import FilmOrchestrator, FilmRequest
from film_pipeline.store import FilmJobStore
from app.api.v1.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter()


class FilmCreateRequest(BaseModel):
    script: str = Field(min_length=1)
    target_seconds: int = Field(default=10_800, ge=5)
    aspect_ratio: str = "16:9"
    style: str = "cinematic"
    image_refs: list[str] = Field(default_factory=list)
    character_refs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Approved character sheet/portrait URLs keyed by character name.",
    )
    seed: Optional[int] = 20_260_826
    bible: Optional[Dict[str, Any]] = None
    admission_mode: Literal["refuse", "waves"] = "refuse"
    backend: Literal["mock", "live"] = "mock"
    live: bool = False
    max_clips: int = Field(default=0, ge=0)
    allow_slates: bool = False
    slate_fraction_limit: float = Field(default=0.05, ge=0.0, le=1.0)


class CrewFilmAdmissionRequest(BaseModel):
    """A Director-approved seven-stage package ready for durable local admission.

    This endpoint intentionally has no ``backend``/``live`` switches. It only creates
    the durable plan using the zero-credit in-process service; scheduling paid motion
    remains the separately gated durable film API operation.
    """
    crew_outputs: Dict[str, Any]
    target_seconds: Optional[int] = Field(default=None, ge=5)
    aspect_ratio: str = "16:9"
    image_refs: list[str] = Field(default_factory=list)
    character_refs: Dict[str, Any] = Field(default_factory=dict)


def _approved_https_refs(values: list[str] | Dict[str, Any]) -> list[str] | Dict[str, list[str]]:
    """Accept only provider-safe approved references; never fetch caller URLs here."""
    from film_pipeline.shots import normalize_character_refs

    if isinstance(values, dict):
        normalized = normalize_character_refs(values)
        candidates = [url for urls in normalized.values() for url in urls]
    else:
        normalized = None
        candidates = values
    if len(candidates) > 32:
        raise ValueError("at most 32 approved image references may be attached to one film")
    for raw in candidates:
        parsed = urlparse(str(raw))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("approved image references must be absolute HTTPS URLs")
    return normalized if normalized is not None else [str(value) for value in candidates]


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


def _ensure_film_access(film_id: str, user: User) -> None:
    owner_id = _services.store.film_owner(film_id)
    if owner_id is None:
        # Pre-SaaS local artifacts have no tenant owner and are intentionally not
        # surfaced to customers. The owner can inspect/migrate them out of band.
        raise HTTPException(status_code=404, detail="film not found")
    if owner_id != user.id and not user.is_superuser:
        raise HTTPException(status_code=404, detail="film not found")


@router.post("/")
async def create_film(request: FilmCreateRequest, user: User = Depends(get_current_user)):
    if request.backend == "live" and (not request.live or request.max_clips <= 0):
        raise HTTPException(
            status_code=400,
            detail="live generation requires both live=true and a positive max_clips safety cap",
        )
    orchestrator = _services.get(request.backend, max_clips=request.max_clips)
    try:
        result = await orchestrator.request_film(FilmRequest(
            script=request.script, target_seconds=request.target_seconds, aspect_ratio=request.aspect_ratio,
            style=request.style, image_refs=request.image_refs, character_refs=request.character_refs,
            seed=request.seed, bible=request.bible,
            admission_mode=request.admission_mode,
            max_clips=request.max_clips if request.backend == "live" else None,
            allow_slates=request.allow_slates,
            slate_fraction_limit=request.slate_fraction_limit,
            tenant_scope=user.id,
        ))
        film_id = str((result.get("film") or {}).get("id") or "")
        if not film_id or not _services.store.claim_film_owner(film_id, user.id):
            raise HTTPException(status_code=409, detail="film belongs to another account")
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"film planning/admission failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if request.backend == "live":
            await orchestrator.aclose()


@router.post("/crew-admissions")
async def admit_crew_film(request: CrewFilmAdmissionRequest, user: User = Depends(get_current_user)):
    """Persist an approved crew package without contacting a generation provider."""
    try:
        image_refs = _approved_https_refs(request.image_refs)
        character_refs = _approved_https_refs(request.character_refs)
        result = await admit_approved_crew_film(
            _services.get("mock"),
            request.crew_outputs,
            target_seconds=request.target_seconds,
            aspect_ratio=request.aspect_ratio,
            image_refs=image_refs,
            character_refs=character_refs,
            tenant_scope=user.id,
        )
        film_id = str(((result.get("admission") or {}).get("film") or {}).get("id") or "")
        if not film_id or not _services.store.claim_film_owner(film_id, user.id):
            raise HTTPException(status_code=409, detail="film belongs to another account")
        return result
    except (CrewHandoffError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"crew film admission failed: {type(exc).__name__}: {exc}") from exc


@router.get("/{film_id}")
async def get_film(film_id: str, user: User = Depends(get_current_user)):
    try:
        _ensure_film_access(film_id, user)
        return _services.store.summary(film_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{film_id}/tick")
async def tick_film(
    film_id: str,
    backend: Literal["mock", "live"] = "mock",
    live: bool = False,
    max_clips: int = 0,
    user: User = Depends(get_current_user),
):
    if backend == "live" and (not live or max_clips <= 0):
        raise HTTPException(status_code=400, detail="live scheduling requires live=true and a positive max_clips safety cap")
    orchestrator = _services.get(backend, max_clips=max_clips)
    try:
        _ensure_film_access(film_id, user)
        return await orchestrator.tick(film_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"film scheduler tick failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if backend == "live":
            await orchestrator.aclose()
