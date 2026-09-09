"""Retired OiiOii project-pipeline routes.

The original project-pipeline handlers executed the seven-stage crew directly
inside this application and selected adapters from ``ProviderRegistry``. That
created a second, unauditable supply path beside the durable ``/films`` graph.

The frontend now uses ``/api/v1/films/crew-runs`` and ``/films/{id}/tick``.
These route shapes stay mounted only so stale clients receive an explicit,
authenticated migration response; they never instantiate a provider, spend a
credit, or call an upstream endpoint.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.endpoints.legacy import require_legacy_demo_mode
from app.models.user import User

router = APIRouter()


class PipelineRunRequest(BaseModel):
    """Compatibility request shape for the retired one-call route."""

    idea: str
    style: Optional[str] = "Anime"
    aspect_ratio: Optional[str] = "16:9"
    model: Optional[str] = None


class PipelineAnimateRequest(BaseModel):
    """Compatibility request shape for the retired animation route."""

    scenes: List[Dict[str, Any]]
    model: Optional[str] = None


SEVEN_STAGES = [
    "Scriptwriter",
    "Art Director",
    "Character Designer",
    "Scene Designer",
    "Storyboard Artist",
    "Animator",
    "Sound Director",
]


async def _retired(*, user: User = Depends(get_current_user)) -> None:
    """Return the common fail-closed retirement response.

    ``user`` is intentionally retained even though the helper never reaches
    generation code: stale requests must not turn an unauthenticated route
    into a public capability probe, and the parent router's dependency remains
    visible in OpenAPI and tests.
    """

    del user
    require_legacy_demo_mode()


@router.post("/{project_id}/pipeline/run")
async def run_pipeline_full(
    project_id: str,
    request: PipelineRunRequest,
    user: User = Depends(get_current_user),
) -> None:
    del project_id, request
    await _retired(user=user)


@router.post("/{project_id}/pipeline/scriptwriter")
async def run_pipeline_scriptwriter(
    project_id: str,
    request: PipelineRunRequest,
    user: User = Depends(get_current_user),
) -> None:
    del project_id, request
    await _retired(user=user)


@router.post("/{project_id}/pipeline/animate")
async def run_pipeline_animate(
    project_id: str,
    request: PipelineAnimateRequest,
    user: User = Depends(get_current_user),
) -> None:
    del project_id, request
    await _retired(user=user)
