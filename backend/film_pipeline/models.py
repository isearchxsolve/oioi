"""Small typed representations of the frozen chat/video HTTP contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


VideoStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class ChatReply:
    text: str
    provider: Optional[str] = None
    session: Optional[str] = None
    tenant: Optional[str] = None


@dataclass(frozen=True)
class VideoSubmission:
    job_id: str
    provider: str
    estimated_seconds: int
    credits_reserved: float
    idempotent_replay: bool = False
    session: Optional[str] = None
    tenant: Optional[str] = None
    #: Some consumer routes return a completed delivery URL inline instead of an
    #: asynchronous job contract. Persist that completion immediately; do not keep
    #: its only receipt in a process-local client map.
    status: VideoStatus = "queued"
    url: Optional[str] = None
    error: Optional[str] = None
    credits_spent: float = 0.0


@dataclass(frozen=True)
class VideoJob:
    job_id: str
    status: VideoStatus
    provider: str
    progress: float
    url: Optional[str]
    error: Optional[str]
    credits_spent: float


@dataclass(frozen=True)
class CapacitySeat:
    seat: str
    provider: str
    credits_remaining: float
    clips_remaining: int
    cooldown_until: Optional[str]


@dataclass(frozen=True)
class VideoCapacity:
    seats: List[CapacitySeat]
    total_clips_available: int


class VideoRouterError(RuntimeError):
    """Base class for errors returned by the frozen video contract."""


class VideoNoCapacity(VideoRouterError):
    def __init__(self, retry_after_seconds: int = 120) -> None:
        self.retry_after_seconds = max(1, int(retry_after_seconds or 120))
        super().__init__(f"video router has no capacity; retry after {self.retry_after_seconds}s")


class VideoTransientError(VideoRouterError):
    pass


class VideoSubmissionUnknown(VideoRouterError):
    """A POST may have reached the router, but no receipt was received.

    The consumer contract has no durable job lookup endpoint, so automatic replay
    could buy a duplicate clip. The scheduler quarantines this state for an
    operator/provider reconciliation rather than pretending it is retryable.
    """


class VideoWallError(VideoRouterError):
    pass


class VideoAuthError(VideoRouterError):
    pass


def classify_video_failure(error: Optional[str]) -> type[VideoRouterError]:
    """Classify terminal router errors without guessing or retrying credential walls."""
    text = (error or "").strip().lower()
    if text.startswith("wall:"):
        return VideoWallError
    if text.startswith("auth:"):
        return VideoAuthError
    return VideoTransientError


@dataclass(frozen=True)
class ShotSpec:
    index: int
    prompt: str
    duration_seconds: int = 5
    image_refs: List[str] = field(default_factory=list)
    seed: Optional[int] = None
    continuity: Dict[str, Any] = field(default_factory=dict)
    #: Director-selected hero shots consume scarce true-motion capacity before ordinary coverage.
    hero_shot: bool = False
    canonical_index: Optional[int] = None
