"""Run configuration and the context object threaded through every agent.

Kept in its own module so :mod:`studio_pipeline.agents` and the orchestrator in
``agent_pipeline`` can both import it without a cycle.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from .events import EventBus, EventType, PipelineStage, STAGE_AGENTS
from .omniroute import OmniRouteClient
from .store import RunStore


class PipelineCancelled(Exception):
    """Raised inside an agent when the run has been cancelled."""


@dataclass
class RunConfig:
    """Everything the operator can dial for one production.

    Defaults describe the headline case from the brief: a 3-hour feature in five acts.
    """

    idea: str
    style: str = "Anime"
    aspect_ratio: str = "16:9"
    #: Target runtime. 10800s = 3 hours.
    target_seconds: int = 10800
    acts: int = 5
    scenes_per_sequence: int = 12
    #: The brief asks for 10-30 second shots; the Scene Designer clamps to this range.
    min_scene_seconds: float = 10.0
    max_scene_seconds: float = 30.0
    language: str = "en"
    #: Simultaneous scene renders. Each one runs an ffmpeg encode plus an HTTP fetch, so
    #: this trades wall-clock against CPU and provider rate limits.
    scene_concurrency: int = 3
    narrate: bool = True
    music: bool = True
    #: "auto" probes OmniRoute and falls back to local synthesis; "omniroute" forces the
    #: provider and fails loudly; "synthesis" skips the probe entirely.
    video_source: str = "auto"
    #: Cap on scenes actually rendered. 0 = no cap. Use a small value for a smoke test
    #: of the whole machine without waiting hours.
    max_scenes: int = 0
    seed: int = 20260822

    def __post_init__(self) -> None:
        self.acts = max(1, int(self.acts))
        self.scenes_per_sequence = max(1, int(self.scenes_per_sequence))
        self.min_scene_seconds = max(1.0, float(self.min_scene_seconds))
        self.max_scene_seconds = max(self.min_scene_seconds, float(self.max_scene_seconds))
        self.target_seconds = max(int(self.min_scene_seconds), int(self.target_seconds))
        self.scene_concurrency = max(1, int(self.scene_concurrency))

    @property
    def avg_scene_seconds(self) -> float:
        return (self.min_scene_seconds + self.max_scene_seconds) / 2.0

    @property
    def target_scene_count(self) -> int:
        """How many scenes are needed to reach the target runtime."""
        return max(1, math.ceil(self.target_seconds / self.avg_scene_seconds))

    @property
    def scenes_per_act(self) -> int:
        return max(1, math.ceil(self.target_scene_count / self.acts))

    @property
    def sequences_per_act(self) -> int:
        return max(1, math.ceil(self.scenes_per_act / self.scenes_per_sequence))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.update(
            target_scene_count=self.target_scene_count,
            scenes_per_act=self.scenes_per_act,
            sequences_per_act=self.sequences_per_act,
        )
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunConfig":
        fields = {
            "idea", "style", "aspect_ratio", "target_seconds", "acts",
            "scenes_per_sequence", "min_scene_seconds", "max_scene_seconds",
            "language", "scene_concurrency", "narrate", "music", "video_source",
            "max_scenes", "seed",
        }
        return cls(**{k: v for k, v in (d or {}).items() if k in fields})


@dataclass
class AgentContext:
    """Shared services + run-scoped mutable state handed to each agent."""

    run_id: str
    config: RunConfig
    store: RunStore
    bus: EventBus
    client: OmniRouteClient
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    #: Set by the API when a human asks for changes instead of approving.
    revision_notes: Optional[str] = None
    stage: PipelineStage = PipelineStage.QUEUED
    #: Pooled client for third-party media fetches. Deliberately separate from the
    #: OmniRoute client so the gateway's Authorization header is never sent to
    #: Pollinations or Google, and so hundreds of downloads reuse connections instead of
    #: burning through Windows ephemeral ports.
    _media_http: Optional[httpx.AsyncClient] = field(default=None, repr=False)

    async def http(self) -> httpx.AsyncClient:
        if self._media_http is None or self._media_http.is_closed:
            self._media_http = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, read=300.0),
                limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
            )
        return self._media_http

    async def aclose(self) -> None:
        if self._media_http is not None and not self._media_http.is_closed:
            await self._media_http.aclose()
        self._media_http = None

    # ------------------------------------------------------------------- events
    async def emit(
        self,
        type: EventType,
        message: str = "",
        *,
        stage: Optional[PipelineStage] = None,
        **data: Any,
    ) -> None:
        await self.bus.publish(type, stage or self.stage, message, **data)

    async def log(self, message: str, **data: Any) -> None:
        await self.emit(EventType.LOG, message, **data)

    async def warn(self, message: str, **data: Any) -> None:
        await self.emit(EventType.WARNING, message, **data)

    async def progress(self, message: str, *, done: int, total: int, **data: Any) -> None:
        pct = round(100.0 * done / total, 1) if total else 0.0
        await self.emit(
            EventType.STAGE_PROGRESS,
            message,
            done=done,
            total=total,
            percent=pct,
            **data,
        )

    async def artifact(self, kind: str, message: str = "", **data: Any) -> None:
        await self.emit(EventType.ARTIFACT, message, kind=kind, **data)

    async def enter_stage(self, stage: PipelineStage, message: str = "") -> None:
        """Transition the state machine, persist it, and announce it."""
        self.stage = stage
        agent = STAGE_AGENTS.get(stage, stage.value)
        self.store.patch_state(stage=stage.value, agent=agent, last_seq=self.bus.last_seq)
        await self.emit(
            EventType.STAGE_STARTED,
            message or f"{agent} started",
            stage=stage,
            agent=agent,
        )

    async def complete_stage(self, message: str = "", **data: Any) -> None:
        agent = STAGE_AGENTS.get(self.stage, self.stage.value)
        self.store.patch_state(last_seq=self.bus.last_seq)
        await self.emit(
            EventType.STAGE_COMPLETED,
            message or f"{agent} finished",
            agent=agent,
            **data,
        )

    # -------------------------------------------------------------- checkpoints
    def checkpoint(
        self,
        stage_label: str,
        status: str,
        *,
        facts: Optional[List[str]] = None,
        next_action: str = "",
        files: Optional[List[str]] = None,
    ) -> None:
        """Dump progress to the run worklog and MASTER_WORKLOG.md immediately.

        Synchronous and fsynced on purpose - if the process dies on the next line, the
        log already names the stage that was in flight.
        """
        self.store.worklog(
            stage_label,
            status,
            facts=facts,
            next_action=next_action,
            files=files,
        )

    # ------------------------------------------------------------ cancellation
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise PipelineCancelled(f"run {self.run_id} cancelled")

    def scene_seed(self, scene_id: int) -> int:
        """Deterministic per-scene image seed.

        Stable across retries and resumes, so re-rendering a scene reproduces the same
        frame instead of a different-looking one spliced into the middle of a cut.
        """
        return (self.config.seed * 1_000_003 + scene_id * 7919) % 2_147_483_647


__all__ = ["AgentContext", "PipelineCancelled", "RunConfig"]
