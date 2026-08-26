"""Admission-controlled, durable asynchronous film scheduler."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from .assembly import ClipMaterializer, HttpClipMaterializer, IncrementalAssembler
from .clients import ChatPoolClient, VideoRouterClient
from .models import VideoAuthError, VideoNoCapacity, VideoTransientError, VideoWallError
from .shots import ShotListPlanner, job_key_for_shot, request_key_for_film
from .store import FilmJobStore


AdmissionMode = Literal["refuse", "waves"]


@dataclass(frozen=True)
class FilmRequest:
    script: str
    target_seconds: int = 10_800
    aspect_ratio: str = "16:9"
    style: str = "cinematic"
    image_refs: List[str] = field(default_factory=list)
    seed: Optional[int] = 20_260_826
    bible: Optional[Dict[str, Any]] = None
    admission_mode: AdmissionMode = "refuse"
    #: Mandatory for live callers; prevents an accidental 2,160-job fan-out.
    max_clips: Optional[int] = None


class FilmOrchestrator:
    """The consumption-layer scheduler; safe to reconstruct after a process restart."""

    def __init__(
        self,
        *,
        store: FilmJobStore,
        chat: ChatPoolClient,
        video: VideoRouterClient,
        artifact_root: Path | str,
        materializer: Optional[ClipMaterializer] = None,
        per_provider_cap: int = 1,
        per_seat_cap: int = 1,
        max_attempts: int = 3,
        poll_interval_seconds: float = 5.0,
        segment_size: int = 60,
        execution_backend: Literal["mock", "live"] = "mock",
        live: bool = False,
        max_clips: Optional[int] = None,
    ) -> None:
        self.store = store
        self.chat = chat
        self.video = video
        self.planner = ShotListPlanner(chat)
        self.materializer = materializer or HttpClipMaterializer()
        self.assembler = IncrementalAssembler(store, artifact_root, segment_size=segment_size)
        # Breadth rule: one is intentionally the default, even if many seats exist.
        self.per_provider_cap = max(1, int(per_provider_cap))
        self.per_seat_cap = max(1, int(per_seat_cap))
        self.max_attempts = max(1, int(max_attempts))
        self.poll_interval_seconds = max(5.0, float(poll_interval_seconds))
        self.execution_backend = execution_backend
        self.live_max_clips = int(max_clips or 0)
        if self.execution_backend == "live" and (not live or self.live_max_clips <= 0):
            raise ValueError("live video requires explicit live=True and a positive max_clips safety cap")

    async def aclose(self) -> None:
        await self.chat.aclose()
        await self.video.aclose()

    async def request_film(self, request: FilmRequest) -> Dict[str, Any]:
        """Cache planning, perform admission control, then persist an idempotent job graph."""
        if not request.script.strip():
            raise ValueError("script must not be empty")
        target_seconds = max(5, int(request.target_seconds))
        if self.execution_backend == "live" and request.max_clips is None:
            raise ValueError("live film requests require a positive per-request max_clips cap")
        if self.execution_backend == "live" and int(request.max_clips or 0) > self.live_max_clips:
            raise ValueError("request max_clips exceeds this live orchestrator's explicit safety cap")
        stable_input_bible = request.bible or {"style": request.style, "imageRefs": request.image_refs}
        request_key = request_key_for_film(
            script=request.script, target_seconds=target_seconds, aspect_ratio=request.aspect_ratio,
            bible=stable_input_bible, seed=request.seed,
        )
        existing = self.store.get_film_by_request_key(request_key)
        if existing is not None:
            return {"film": self.store.summary(existing["id"]), "idempotent_replay": True}

        bible = request.bible or await self.planner.create_bible(
            request.script, style=request.style, image_refs=request.image_refs
        )
        shots = await self.planner.decompose(
            request.script, target_seconds=target_seconds, bible=bible, seed=request.seed
        )
        canonical = {shot.canonical_index if shot.canonical_index is not None else shot.index: shot for shot in shots}
        capacity = await self.video.capacity()  # mandatory before accepting paid work
        required = len(canonical)
        if request.max_clips is not None and required > max(0, int(request.max_clips)):
            film = self.store.create_film(
                request_key=request_key, script=request.script, target_seconds=target_seconds,
                aspect_ratio=request.aspect_ratio, bible=bible, status="refused_safety_cap",
                admission_mode=request.admission_mode, capacity_at_admission=capacity.total_clips_available,
            )
            self.store.set_film_status(
                film["id"], "refused_safety_cap",
                error=f"live safety cap is {int(request.max_clips)} clips but plan requires {required} unique clips",
            )
            return {
                "film": self.store.summary(film["id"]), "accepted": False,
                "required_unique_clips": required, "max_clips": int(request.max_clips),
                "shortfall": required - int(request.max_clips),
            }
        status = "admitted" if capacity.total_clips_available >= required else (
            "wave_scheduled" if request.admission_mode == "waves" else "refused_capacity"
        )
        film = self.store.create_film(
            request_key=request_key, script=request.script, target_seconds=target_seconds,
            aspect_ratio=request.aspect_ratio, bible=bible, status=status, admission_mode=request.admission_mode,
            capacity_at_admission=capacity.total_clips_available,
        )
        # Another process may have completed the plan while this process was calling chat.
        if film["logical_shots"]:
            return {"film": self.store.summary(film["id"]), "idempotent_replay": True}
        shortfall = max(0, required - capacity.total_clips_available)
        if status == "refused_capacity":
            self.store.set_film_status(
                film["id"], status,
                error=f"capacity shortfall: requires {required} unique clips; {capacity.total_clips_available} available; shortfall {shortfall}",
            )
            return {
                "film": self.store.summary(film["id"]), "accepted": False, "required_unique_clips": required,
                "available_clips": capacity.total_clips_available, "shortfall": shortfall,
            }

        job_keys = {
            index: job_key_for_shot(shot, canonical_index=index) for index, shot in canonical.items()
        }
        self.store.add_shots_and_jobs(film["id"], shots, aspect_ratio=request.aspect_ratio, job_keys=job_keys)
        return {
            "film": self.store.summary(film["id"]), "accepted": True,
            "required_unique_clips": required, "logical_shots": len(shots),
            "available_clips": capacity.total_clips_available, "shortfall": shortfall,
            "capacity_strategy": request.admission_mode,
        }

    def _choose_seat(self, capacity: Any, *, remaining: Optional[Dict[str, int]] = None) -> Optional[Any]:
        unavailable = self.store.unavailable_seats()
        choices = []
        for seat in capacity.seats:
            available = (remaining or {}).get(seat.seat, seat.clips_remaining)
            if available <= 0 or (seat.seat, seat.provider) in unavailable:
                continue
            if self.store.provider_inflight(seat.provider) >= self.per_provider_cap:
                continue
            if self.store.jobs_using_seat(seat.provider, seat.seat) >= self.per_seat_cap:
                continue
            choices.append(seat)
        # Least inflight then greatest remaining capacity: breadth, never depth.
        choices.sort(key=lambda s: (self.store.jobs_using_seat(s.provider, s.seat), -(remaining or {}).get(s.seat, s.clips_remaining), s.seat))
        return choices[0] if choices else None

    @staticmethod
    def _backoff(attempts: int) -> float:
        return min(15 * 60.0, 5.0 * (2 ** max(0, attempts - 1)))

    async def _materialize_completed(self, film_id: str, counts: Dict[str, int]) -> None:
        for job in self.store.jobs_needing_materialization(film_id):
            try:
                await self.assembler.materialize_job(film_id, job, self.materializer)
                counts["materialized"] += 1
            except Exception as exc:  # remote render is safe; only local retrieval is retried
                self.store.defer(
                    job["job_key"], status="succeeded", seconds=0,
                    error=f"local materialization pending: {type(exc).__name__}: {exc}",
                )
                counts["materialization_errors"] += 1

    async def tick(self, film_id: str) -> Dict[str, Any]:
        """Advance a film once.  Call periodically from a worker/scheduler or API task.

        This is intentionally bounded: each tick polls only due jobs and submits only
        seats permitted by capacity and both concurrency caps.
        """
        film = self.store.get_film(film_id)
        if not film:
            raise KeyError(f"film {film_id} does not exist")
        if film["status"] == "refused_capacity":
            return {"film": self.store.summary(film_id), "actions": {"refused": 1}}
        if self.execution_backend == "live" and len(self.store.jobs_for_film(film_id)) > self.live_max_clips:
            raise ValueError("refusing live tick: durable job graph exceeds the explicit max_clips cap")
        counts: Dict[str, int] = {
            "polled": 0, "submitted": 0, "parked_capacity": 0, "retrying": 0,
            "quarantined": 0, "parked_wall": 0, "concurrency_limited": 0,
            "materialized": 0, "materialization_errors": 0,
        }

        # Poll existing work first.  Store enforces the frozen >=5 s/job interval.
        for job in self.store.due_polls(film_id, poll_interval_seconds=self.poll_interval_seconds):
            try:
                remote = await self.video.get_job(job["remote_job_id"])
                counts["polled"] += 1
                self.store.mark_poll(
                    job["job_key"], status=remote.status, provider=remote.provider, url=remote.url,
                    error=remote.error, credits_spent=remote.credits_spent,
                )
                if remote.status != "failed":
                    continue
                error_type = self.video.terminal_exception(remote.error)
                if isinstance(error_type, (VideoWallError, VideoAuthError)):
                    self.store.mark_seat_unavailable(str(job.get("seat") or ""), remote.provider, remote.error or "")
                    self.store.defer(job["job_key"], status="parked_wall", seconds=0, error=remote.error or "wall/auth failure")
                    counts["parked_wall"] += 1
                elif int(job["attempts"]) >= self.max_attempts:
                    self.store.quarantine(job["job_key"], remote.error or "repeated terminal failure")
                    counts["quarantined"] += 1
                else:
                    self.store.defer(
                        job["job_key"], status="retry_wait", seconds=self._backoff(int(job["attempts"])),
                        error=remote.error or "transient remote failure",
                    )
                    counts["retrying"] += 1
            except VideoTransientError as exc:
                attempts = self.store.record_attempt(job["job_key"])
                if attempts >= self.max_attempts:
                    self.store.quarantine(job["job_key"], str(exc))
                    counts["quarantined"] += 1
                else:
                    self.store.defer(job["job_key"], status="retry_wait", seconds=self._backoff(attempts), error=str(exc))
                    counts["retrying"] += 1

        await self._materialize_completed(film_id, counts)
        capacity = await self.video.capacity()
        # A wave-scheduled film can progress when capacity returns; never silently spin when it does not.
        capacity_remaining = {seat.seat: seat.clips_remaining for seat in capacity.seats}
        for job in self.store.due_jobs(film_id, limit=max(1, capacity.total_clips_available)):
            seat = self._choose_seat(capacity, remaining=capacity_remaining)
            if seat is None:
                # There may be real capacity but every eligible provider/seat is at its
                # deliberately narrow concurrency cap.  Leave work pending instead of
                # mislabeling it as provider exhaustion or delaying it for a whole minute.
                if any(value > 0 for value in capacity_remaining.values()):
                    counts["concurrency_limited"] += 1
                    break
                self.store.defer(job["job_key"], status="parked_capacity", seconds=60, error="waiting for provider capacity")
                counts["parked_capacity"] += 1
                continue
            try:
                submitted = await self.video.submit(
                    job_key=job["job_key"], prompt=job["prompt"], duration_seconds=job["duration_seconds"],
                    image_refs=job["image_refs"], aspect_ratio=job["aspect_ratio"], seed=job["seed"],
                )
                # The frozen contract reports provider but not seat.  ``seat`` is the consumer-side
                # admission assignment used for rate caps; see the report for that contract limit.
                self.store.mark_submitted(
                    job["job_key"], remote_job_id=submitted.job_id, provider=submitted.provider,
                    seat=seat.seat, credits_reserved=submitted.credits_reserved,
                )
                capacity_remaining[seat.seat] = max(0, capacity_remaining.get(seat.seat, 0) - 1)
                counts["submitted"] += 1
            except VideoNoCapacity as exc:
                self.store.defer(job["job_key"], status="parked_capacity", seconds=exc.retry_after_seconds, error=str(exc))
                counts["parked_capacity"] += 1
            except VideoTransientError as exc:
                attempts = self.store.record_attempt(job["job_key"])
                if attempts >= self.max_attempts:
                    self.store.quarantine(job["job_key"], str(exc))
                    counts["quarantined"] += 1
                else:
                    self.store.defer(job["job_key"], status="retry_wait", seconds=self._backoff(attempts), error=str(exc))
                    counts["retrying"] += 1

        await self._materialize_completed(film_id, counts)
        try:
            final = await self.assembler.assemble_available(film_id)
            if final:
                counts["finalized"] = 1
            elif self.store.get_film(film_id)["status"] not in {"wave_scheduled", "completed"}:
                self.store.set_film_status(film_id, "running")
        except Exception as exc:
            self.store.set_film_status(film_id, "assembly_error", error=f"{type(exc).__name__}: {exc}")
            counts["assembly_errors"] = 1
        return {"film": self.store.summary(film_id), "actions": counts}

    async def run_until_idle(self, film_id: str, *, max_ticks: int = 100, sleep_seconds: float = 5.0) -> Dict[str, Any]:
        """Bounded helper for operators/tests; never an unbounded submit loop."""
        latest: Dict[str, Any] = {}
        for _ in range(max(1, int(max_ticks))):
            latest = await self.tick(film_id)
            states = latest["film"]["job_states"]
            if latest["film"]["status"] in {"completed", "refused_capacity", "assembly_error"}:
                return latest
            if not any(state in states for state in ("pending", "queued", "running", "retry_wait")):
                return latest
            await asyncio.sleep(max(0.0, sleep_seconds))
        return latest
