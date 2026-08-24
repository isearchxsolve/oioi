"""Event types and the fan-out bus that feeds SSE / WebSocket subscribers.

A 3-hour render emits thousands of events over hours. Two consequences shape this
module:

1.  Subscribers *will* disconnect. Every event carries a monotonically increasing
    ``seq``, and :meth:`EventBus.subscribe` can replay from any ``seq`` by reading the
    durable journal on disk before switching to the live queue. Reconnect is lossless.
2.  A slow subscriber must never stall the pipeline. Each subscriber gets its own
    bounded queue; when it overflows the *subscriber* is marked lagging and gets a
    ``GAP`` event telling it to re-fetch full state. Publishing never blocks.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional


class PipelineStage(str, Enum):
    """States of the production state machine.

    Order matters: :func:`stage_index` uses declaration order to decide whether a
    persisted run has already passed a given stage, which is how resume works.
    """

    QUEUED = "queued"
    SCRIPTWRITING = "scriptwriting"            # Agent 1 — Scriptwriter
    AWAITING_APPROVAL = "awaiting_approval"    # Agent 2 — Interactive Feedback Pause
    ART_DIRECTION = "art_direction"            # Agent 3 — Art Director & Character Designer
    SCENE_DESIGN = "scene_design"              # Agent 4 — Scene Designer
    ANIMATION = "animation"                    # Agent 5 — Animator
    SOUND_DESIGN = "sound_design"              # Agent 6 — Sound Director
    DIRECTING = "directing"                    # Agent 7 — Director (FFmpeg stitch)
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Declaration order of the productive stages, used for resume comparisons.
STAGE_ORDER: List[PipelineStage] = [
    PipelineStage.QUEUED,
    PipelineStage.SCRIPTWRITING,
    PipelineStage.AWAITING_APPROVAL,
    PipelineStage.ART_DIRECTION,
    PipelineStage.SCENE_DESIGN,
    PipelineStage.ANIMATION,
    PipelineStage.SOUND_DESIGN,
    PipelineStage.DIRECTING,
    PipelineStage.COMPLETED,
]

#: Human labels for the 7 agents, keyed by the stage they own.
STAGE_AGENTS: Dict[PipelineStage, str] = {
    PipelineStage.SCRIPTWRITING: "Scriptwriter",
    PipelineStage.AWAITING_APPROVAL: "Interactive Feedback Pause",
    PipelineStage.ART_DIRECTION: "Art Director & Character Designer",
    PipelineStage.SCENE_DESIGN: "Scene Designer",
    PipelineStage.ANIMATION: "Animator",
    PipelineStage.SOUND_DESIGN: "Sound Director",
    PipelineStage.DIRECTING: "Director",
}


def stage_index(stage: PipelineStage) -> int:
    """Position of ``stage`` in :data:`STAGE_ORDER`; terminal states sort last."""
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return len(STAGE_ORDER)  # FAILED / CANCELLED


class EventType(str, Enum):
    RUN_CREATED = "run.created"
    STAGE_STARTED = "stage.started"
    STAGE_PROGRESS = "stage.progress"
    STAGE_COMPLETED = "stage.completed"
    ARTIFACT = "artifact"                  # a scene, character sheet, clip, audio bed…
    AWAITING_APPROVAL = "approval.awaiting"
    APPROVED = "approval.granted"
    REVISION_REQUESTED = "approval.revision"
    LOG = "log"
    WARNING = "warning"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    GAP = "gap"                            # subscriber fell behind; re-fetch state
    DONE = "done"                          # terminal; stream closes after this


@dataclass
class Event:
    seq: int
    ts: float
    run_id: str
    type: EventType
    stage: PipelineStage
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["stage"] = self.stage.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    def to_sse(self) -> str:
        """Server-Sent Events framing. ``id:`` enables ``Last-Event-ID`` replay."""
        return f"id: {self.seq}\nevent: {self.type.value}\ndata: {self.to_json()}\n\n"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Event":
        return cls(
            seq=int(d["seq"]),
            ts=float(d.get("ts", 0.0)),
            run_id=str(d.get("run_id", "")),
            type=EventType(d["type"]),
            stage=PipelineStage(d.get("stage", PipelineStage.QUEUED.value)),
            message=d.get("message", "") or "",
            data=d.get("data") or {},
        )


class _Subscriber:
    __slots__ = ("queue", "lagging")

    def __init__(self, maxsize: int) -> None:
        self.queue: asyncio.Queue[Optional[Event]] = asyncio.Queue(maxsize=maxsize)
        self.lagging = False


class EventBus:
    """Fan-out of pipeline events to any number of live subscribers.

    ``journal_reader`` is an optional callable returning an iterable of persisted
    event dicts; it lets :meth:`subscribe` replay history that predates the
    subscription. Injected rather than imported so the bus stays testable without a
    filesystem.
    """

    def __init__(
        self,
        run_id: str,
        *,
        journal_reader: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        on_publish: Optional[Callable[[Event], None]] = None,
        queue_size: int = 2048,
    ) -> None:
        self.run_id = run_id
        self._journal_reader = journal_reader
        self._on_publish = on_publish
        self._queue_size = queue_size
        self._subscribers: List[_Subscriber] = []
        self._seq = 0
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def last_seq(self) -> int:
        return self._seq

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(
        self,
        type: EventType,
        stage: PipelineStage,
        message: str = "",
        **data: Any,
    ) -> Event:
        """Persist then fan out one event. Never blocks on slow subscribers."""
        async with self._lock:
            self._seq += 1
            event = Event(
                seq=self._seq,
                ts=time.time(),
                run_id=self.run_id,
                type=type,
                stage=stage,
                message=message,
                data=data,
            )
            # Durability first: a subscriber that reconnects must be able to see this
            # even if the process dies on the very next line.
            if self._on_publish is not None:
                try:
                    self._on_publish(event)
                except Exception:  # noqa: BLE001 — journaling must never kill a run
                    pass
            targets = list(self._subscribers)

        for sub in targets:
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                if not sub.lagging:
                    sub.lagging = True
                    # Drain half the backlog so the subscriber can catch up, then tell
                    # it explicitly that it lost events.
                    for _ in range(self._queue_size // 2):
                        try:
                            sub.queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    gap = Event(
                        seq=event.seq,
                        ts=time.time(),
                        run_id=self.run_id,
                        type=EventType.GAP,
                        stage=stage,
                        message="Subscriber fell behind; events were dropped. Re-fetch full state.",
                        data={"resume_from": event.seq},
                    )
                    with contextlib.suppress(asyncio.QueueFull):
                        sub.queue.put_nowait(gap)
                    with contextlib.suppress(asyncio.QueueFull):
                        sub.queue.put_nowait(event)
        return event

    def bump_seq_to(self, seq: int) -> None:
        """Continue numbering after a resume so replayed seqs are never reused."""
        self._seq = max(self._seq, int(seq))

    async def subscribe(self, from_seq: int = 0) -> AsyncIterator[Event]:
        """Yield events with ``seq > from_seq``, replaying history first.

        Registration happens *before* the journal is read, so an event published
        during replay lands in the queue and is emitted after (deduplicated by seq)
        rather than being lost in the seam.
        """
        sub = _Subscriber(self._queue_size)
        async with self._lock:
            self._subscribers.append(sub)
            watermark = self._seq
            closed = self._closed

        try:
            if from_seq < watermark and self._journal_reader is not None:
                for raw in self._journal_reader():
                    try:
                        past = Event.from_dict(raw)
                    except Exception:  # noqa: BLE001 — tolerate a torn trailing line
                        continue
                    if from_seq < past.seq <= watermark:
                        yield past
            emitted_through = max(from_seq, watermark)

            if closed:
                return

            while True:
                item = await sub.queue.get()
                if item is None:  # close sentinel
                    return
                if item.seq <= emitted_through and item.type is not EventType.GAP:
                    continue  # already replayed from the journal
                if item.type is not EventType.GAP:
                    emitted_through = item.seq
                yield item
                if item.type is EventType.DONE:
                    return
        finally:
            async with self._lock:
                if sub in self._subscribers:
                    self._subscribers.remove(sub)

    async def close(self) -> None:
        """Release every live subscriber. Idempotent."""
        async with self._lock:
            self._closed = True
            targets = list(self._subscribers)
        for sub in targets:
            with contextlib.suppress(asyncio.QueueFull):
                sub.queue.put_nowait(None)
