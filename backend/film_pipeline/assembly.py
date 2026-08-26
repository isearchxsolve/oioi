"""Incremental ordered assembly for durable clip-job output."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol

from studio_pipeline import media

from .store import FilmJobStore


class ClipMaterializer(Protocol):
    async def materialize(self, *, remote_url: str, destination: Path, duration_seconds: int, aspect_ratio: str) -> Path:
        """Get a completed router clip into the durable local film storage."""


class FallbackClipMaterializer(Protocol):
    """Materialise an ordered shot when the async video pool cannot supply motion.

    The fallback deliberately produces the same uniform local MP4 contract as a router
    clip.  Assembly therefore keeps the original shot order and never has to special-case
    a provider outage, exhausted free seats, or a terminal provider wall.
    """

    async def materialize_fallback(
        self,
        *,
        prompt: str,
        image_refs: List[str],
        seed: Optional[int],
        continuity: Dict[str, Any],
        destination: Path,
        duration_seconds: int,
        aspect_ratio: str,
    ) -> "FallbackMaterialization":
        """Create a playable fallback MP4 and report its fidelity honestly."""


FallbackKind = Literal["kenburns", "slate", "synthetic"]


@dataclass(frozen=True)
class FallbackMaterialization:
    """A local fallback artifact plus the quality tier that produced it."""

    path: Path
    kind: FallbackKind
    detail: Optional[str] = None


class HttpClipMaterializer:
    """Download, normalise, and atomically retain a real router URL for assembly."""

    async def materialize(self, *, remote_url: str, destination: Path, duration_seconds: int, aspect_ratio: str) -> Path:
        if remote_url.startswith("mock://"):
            raise media.MediaError("mock URL needs SyntheticClipMaterializer; no remote URL was fetched")
        source = destination.with_suffix(".source" + (Path(remote_url).suffix or ".mp4"))
        await media.download(remote_url, source)
        width, height = media.resolve_size(aspect_ratio)
        await media.normalize_clip(source, destination, duration=float(duration_seconds), width=width, height=height)
        return destination


class SyntheticClipMaterializer:
    """Generate a valid zero-credit slate clip for mock-only end-to-end tests."""

    def __init__(self, *, width: int = 320, height: int = 180) -> None:
        self.width = max(16, width)
        self.height = max(16, height)

    async def materialize(self, *, remote_url: str, destination: Path, duration_seconds: int, aspect_ratio: str) -> Path:
        # ``remote_url`` is intentionally not fetched: mock:// denotes the local test backend.
        await media.synthesize_slate_clip(
            destination, duration=max(0.5, float(duration_seconds)), width=self.width, height=self.height
        )
        return destination


class KenBurnsFallbackMaterializer:
    """Keyless still-image to motion fallback for every unavailable router clip.

    The primary fallback is a Pollinations still followed by the existing FFmpeg Ken
    Burns synthesiser.  A caller supplied image reference is preferred when available so
    character sheets and approved scene art carry through to the fallback.  If a still
    provider is temporarily unavailable, the final slate tier preserves the exact edit
    slot and duration rather than leaving the film permanently incomplete.
    """

    def __init__(
        self,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        still_request_gap_seconds: float = 1.0,
    ) -> None:
        self.width = width
        self.height = height
        # Cold still requests are intentionally serialized.  Pollinations can queue
        # only one request and communicates its limit as JSON/429, so parallel image
        # fetches reduce fidelity without making the edit faster.
        self._still_fetch_lock = asyncio.Lock()
        self._still_request_gap_seconds = max(0.0, float(still_request_gap_seconds))
        self._last_still_fetch_at = 0.0
        self._still_supply_exhausted = False
        self._still_supply_detail: Optional[str] = None

    @staticmethod
    def _motion(continuity: Dict[str, Any]) -> str:
        shot = continuity.get("shot") if isinstance(continuity, dict) else None
        if not isinstance(shot, dict):
            return "slow push in"
        for key in ("cameraMove", "motion", "camera", "camera_move", "movement"):
            value = shot.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                for nested in ("movement", "move", "motion"):
                    candidate = value.get(nested)
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate
        return "slow push in"

    @staticmethod
    def _reference_url(image_refs: List[str]) -> Optional[str]:
        for ref in image_refs:
            value = str(ref or "").strip()
            if value.startswith(("https://", "http://")):
                return value
        return None

    @staticmethod
    def _usable_still(path: Path) -> bool:
        try:
            return path.is_file() and path.stat().st_size >= 1024
        except OSError:
            return False

    @classmethod
    def _retained_still(cls, still_dir: Path, *, identity: str) -> Optional[Path]:
        """Pick a stable previously fetched scene still after a known quota wall."""
        retained = sorted(path for path in still_dir.glob("*.jpg") if cls._usable_still(path))
        if not retained:
            return None
        return retained[int(identity[:16], 16) % len(retained)]

    @staticmethod
    def _scene_still_request(
        *, prompt: str, seed: Optional[int], continuity: Dict[str, Any]
    ) -> tuple[str, Optional[int]]:
        shot = continuity.get("shot") if isinstance(continuity, dict) else None
        if not isinstance(shot, dict):
            return str(prompt).strip(), seed
        still_prompt = str(shot.get("stillPrompt") or prompt).strip()
        still_seed = shot.get("stillSeed", seed)
        try:
            return still_prompt, int(still_seed) if still_seed is not None else None
        except (TypeError, ValueError):
            return still_prompt, seed

    async def _obtain_still(
        self,
        *,
        still: Path,
        still_dir: Path,
        identity: str,
        source: str,
    ) -> tuple[Path, Optional[str]]:
        """Return a cached/fetched still, or reuse retained art after a quota verdict.

        ``MediaContentTypeError`` represents a definitive non-image response (not a
        retryable network hiccup).  Once seen, no more remote still requests are made
        for this materializer; remaining shot variants use the already-discovered
        supply with their individual camera moves.
        """
        if self._usable_still(still):
            return still, None
        still_dir.mkdir(parents=True, exist_ok=True)
        async with self._still_fetch_lock:
            # Another concurrent Ken Burns render may have filled this exact scene
            # cache entry while this job waited for the single-fetch gate.
            if self._usable_still(still):
                return still, None
            if self._still_supply_exhausted:
                retained = self._retained_still(still_dir, identity=identity)
                if retained is not None:
                    return retained, f"reused retained still after image supply stopped: {self._still_supply_detail}"
                raise media.MediaContentTypeError(
                    f"image supply stopped before any usable still was retained: {self._still_supply_detail}"
                )
            delay = self._still_request_gap_seconds - (time.monotonic() - self._last_still_fetch_at)
            if delay > 0:
                await asyncio.sleep(delay)
            # Count attempts from their start so both successful and failed cold
            # generations respect the provider's one-request queue discipline.
            self._last_still_fetch_at = time.monotonic()
            try:
                await media.download(
                    source, still, timeout=240.0, attempts=3, min_bytes=1024,
                    expected_content_type_prefix="image/",
                )
            except media.MediaContentTypeError as exc:
                self._still_supply_exhausted = True
                self._still_supply_detail = f"{type(exc).__name__}: {exc}"
                retained = self._retained_still(still_dir, identity=identity)
                if retained is not None:
                    return retained, f"reused retained still after image supply stopped: {self._still_supply_detail}"
                raise
            if not self._usable_still(still):
                raise media.MediaError(f"image download produced no usable still: {still}")
            return still, None

    async def materialize_fallback(
        self,
        *,
        prompt: str,
        image_refs: List[str],
        seed: Optional[int],
        continuity: Dict[str, Any],
        destination: Path,
        duration_seconds: int,
        aspect_ratio: str,
    ) -> FallbackMaterialization:
        width, height = media.resolve_size(aspect_ratio)
        width = self.width or width
        height = self.height or height
        # The still belongs to scene/image identity, not one output job. Several
        # different camera moves can cut over the same scene still without paying the
        # rate-limited still service repeatedly.  Include the exact visual request and
        # output geometry so the cache cannot accidentally cross-contaminate formats.
        still_prompt, still_seed = self._scene_still_request(
            prompt=prompt, seed=seed, continuity=continuity,
        )
        identity = media.stable_media_key({
            "stillPrompt": still_prompt,
            "seed": still_seed,
            "width": width,
            "height": height,
        })
        still_dir = destination.parent.parent / "stills"
        still = still_dir / f"{identity}.jpg"
        try:
            source = self._reference_url(image_refs) or media.pollinations_image_url(
                still_prompt, width=width, height=height, seed=still_seed
            )
            still, detail = await self._obtain_still(
                still=still, still_dir=still_dir, identity=identity, source=source,
            )
            await media.synthesize_kenburns_clip(
                still,
                destination,
                duration=max(1.0, float(duration_seconds)),
                width=width,
                height=height,
                motion=self._motion(continuity),
            )
            return FallbackMaterialization(destination, "kenburns", detail)
        except Exception as exc:
            # A provider outage must not turn zero available motion seats into an
            # unfinishable film.  The slate keeps timing aligned, but it is explicitly
            # marked so the scheduler can refuse a deceptively placeholder-heavy final.
            await media.synthesize_slate_clip(
                destination,
                duration=max(1.0, float(duration_seconds)),
                width=width,
                height=height,
            )
            return FallbackMaterialization(
                destination, "slate", f"{type(exc).__name__}: {exc}",
            )


class SyntheticFallbackClipMaterializer:
    """Network-free fallback used by stub and unit end-to-end tests."""

    def __init__(self, *, width: int = 320, height: int = 180) -> None:
        self.width = max(16, width)
        self.height = max(16, height)

    async def materialize_fallback(
        self,
        *,
        prompt: str,
        image_refs: List[str],
        seed: Optional[int],
        continuity: Dict[str, Any],
        destination: Path,
        duration_seconds: int,
        aspect_ratio: str,
    ) -> FallbackMaterialization:
        await media.synthesize_slate_clip(
            destination,
            duration=max(0.5, float(duration_seconds)),
            width=self.width,
            height=self.height,
        )
        return FallbackMaterialization(destination, "synthetic")


class IncrementalAssembler:
    """Build fixed-size contiguous segments, then one final container at completion.

    A newly completed clip is never appended by re-encoding the previous entire film.
    At most one fixed-size segment is encoded per assembly event, which gives a
    2,160-shot film bounded incremental work and recovery checkpoints.
    """

    def __init__(
        self,
        store: FilmJobStore,
        artifact_root: Path | str,
        *,
        segment_size: int = 60,
        transition: str = "hard-cut",
        narration: Optional[Path] = None,
        music: Optional[Path] = None,
    ) -> None:
        self.store = store
        self.root = Path(artifact_root).resolve()
        self.segment_size = max(1, int(segment_size))
        self.transition = transition
        self.narration = narration
        self.music = music

    def clip_path(self, film_id: str, job_key: str) -> Path:
        return self.root / film_id / "clips" / f"{job_key}.mp4"

    async def materialize_job(self, film_id: str, job: Dict[str, object], materializer: ClipMaterializer) -> Path:
        existing = job.get("local_path")
        if existing and await media.is_playable(Path(str(existing))):
            return Path(str(existing))
        remote_url = str(job.get("remote_url") or "")
        if not remote_url:
            raise media.MediaError(f"succeeded job {job['job_key']} has no video URL")
        destination = self.clip_path(film_id, str(job["job_key"]))
        if await media.is_playable(destination):
            self.store.mark_local_success(str(job["job_key"]), str(destination))
            return destination
        path = await materializer.materialize(
            remote_url=remote_url, destination=destination, duration_seconds=int(job["duration_seconds"]),
            aspect_ratio=str(job["aspect_ratio"]),
        )
        if not await media.is_playable(path):
            raise media.MediaError(f"materialized clip is not playable: {path}")
        self.store.mark_local_success(str(job["job_key"]), str(path))
        return path

    async def assemble_available(self, film_id: str, *, allow_finalize: bool = True) -> Optional[Path]:
        """Emit next completed contiguous segment(s); finalise only once all shots resolve."""
        shots = self.store.shots(film_id)
        if not shots:
            return None
        jobs = {job["job_key"]: job for job in self.store.jobs_for_film(film_id)}
        segments = self.store.segments(film_id)
        start = int(segments[-1]["end_shot_index"]) + 1 if segments else 0
        segment_index = len(segments)
        film_dir = self.root / film_id
        segment_dir = film_dir / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)

        while start < len(shots):
            contiguous = []
            for shot in shots[start:]:
                job = jobs.get(shot["job_key"])
                if not job or job["status"] != "succeeded" or not job.get("local_path"):
                    break
                path = Path(str(job["local_path"]))
                if not await media.is_playable(path):
                    break
                contiguous.append(path)
                if len(contiguous) >= self.segment_size:
                    break
            remaining_total = len(shots) - start
            if len(contiguous) < self.segment_size and len(contiguous) != remaining_total:
                break  # preserve ordered playback; wait for the gap, do not build a fake cut
            if not contiguous:
                break
            end = start + len(contiguous) - 1
            destination = segment_dir / f"segment_{segment_index:05d}.mp4"
            manifest = segment_dir / f"segment_{segment_index:05d}.txt"
            if not await media.is_playable(destination):
                # hard-cut is a deliberate, stable transition profile.  Crossfades are optional
                # later because they force re-encoding at segment boundaries.
                await media.concat_copy(contiguous, destination, manifest=manifest)
            self.store.save_segment(
                film_id, segment_index=segment_index, start_shot_index=start, end_shot_index=end,
                path=str(destination), status=f"succeeded:{self.transition}",
            )
            start = end + 1
            segment_index += 1

        segments = self.store.segments(film_id)
        if not segments or int(segments[-1]["end_shot_index"]) != len(shots) - 1:
            return None
        if not allow_finalize:
            # Segment checkpoints remain valuable diagnostics and make an explicit
            # later approval cheap, but a slate-heavy timeline must not acquire the
            # customer-facing final MP4/status until the operator permits it.
            return None
        final_dir = film_dir / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        raw = final_dir / "assembled.mp4"
        final = final_dir / "film.mp4"
        segment_paths = [Path(str(segment["path"])) for segment in segments]
        if not await media.is_playable(raw):
            await media.concat_copy(segment_paths, raw, manifest=final_dir / "final_concat.txt")
        if not await media.is_playable(final):
            await media.mix_final_audio(raw, final, narration=self.narration, music=self.music, loop_music=True)
        self.store.set_film_status(film_id, "completed", output_path=str(final))
        return final
