"""Zero-credit integration tests for the durable film consumption pipeline."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from film_pipeline.assembly import (
    FallbackMaterialization,
    KenBurnsFallbackMaterializer,
    SyntheticClipMaterializer,
    SyntheticFallbackClipMaterializer,
)
from film_pipeline.clients import VideoNoCapacity, VideoRouterClient
from film_pipeline.mock import DeterministicMockChatClient, MockSeat, MockVideoBackend, MockVideoConfig
from film_pipeline.orchestrator import FilmOrchestrator, FilmRequest
from film_pipeline.models import ChatReply, ShotSpec
from film_pipeline.shots import ShotListPlanner, _extract_json, deduplicate_shots, request_key_for_film
from film_pipeline.store import FilmJobStore
from studio_pipeline import media
from studio_pipeline.media import is_playable


def _pipeline(tmp_path: Path, backend: MockVideoBackend) -> FilmOrchestrator:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://mock-video")
    return FilmOrchestrator(
        store=FilmJobStore(tmp_path / "film_jobs.sqlite3"), chat=DeterministicMockChatClient(),
        video=VideoRouterClient(client=http), artifact_root=tmp_path / "artifacts",
        materializer=SyntheticClipMaterializer(width=64, height=36),
        fallback_materializer=SyntheticFallbackClipMaterializer(width=64, height=36),
        segment_size=2,
    )


@pytest.mark.asyncio
async def test_mock_contract_idempotency_and_capacity_exhaustion() -> None:
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=1)]))
    client = VideoRouterClient(client=httpx.AsyncClient(
        transport=httpx.ASGITransport(app=backend.app), base_url="http://mock-video"
    ))
    first = await client.submit(
        job_key="contract-job", prompt="a safe mock shot", duration_seconds=5,
        image_refs=[], aspect_ratio="16:9", seed=None,
    )
    replay = await client.submit(
        job_key="contract-job", prompt="a safe mock shot", duration_seconds=5,
        image_refs=[], aspect_ratio="16:9", seed=None,
    )
    assert first.job_id == replay.job_id
    assert not first.idempotent_replay and replay.idempotent_replay
    assert (await client.capacity()).total_clips_available == 0
    with pytest.raises(VideoNoCapacity):
        await client.submit(
            job_key="capacity-job", prompt="another shot", duration_seconds=5,
            image_refs=[], aspect_ratio="16:9", seed=None,
        )


@pytest.mark.asyncio
async def test_full_mock_pipeline_resume_after_worker_kill_has_no_duplicate_generation(tmp_path: Path) -> None:
    """Reconstructing the consumer after work starts is the kill/restart recovery proof.

    The mock router is deliberately retained as the external supply process would be;
    only the scheduler/store-side object is discarded and rebuilt from SQLite.
    """
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=4)]))
    request = FilmRequest(script="A scout crosses a valley and finds home.", target_seconds=15)
    first_worker = _pipeline(tmp_path, backend)
    admitted = await first_worker.request_film(request)
    film_id = admitted["film"]["id"]
    assert admitted["accepted"]
    assert admitted["required_unique_clips"] == 3
    await first_worker.tick(film_id)  # submitted once, then simulate an abrupt worker death
    assert len(backend.jobs_by_key) == 1
    await first_worker.aclose()

    resumed_worker = _pipeline(tmp_path, backend)
    replay = await resumed_worker.request_film(request)
    assert replay["idempotent_replay"] is True
    assert replay["film"]["id"] == film_id
    for _ in range(8):
        outcome = await resumed_worker.tick(film_id)
        if outcome["film"]["status"] == "completed":
            break
    summary = resumed_worker.store.summary(film_id)
    assert summary["status"] == "completed"
    assert len(backend.jobs_by_key) == summary["unique_jobs"] == 3
    assert summary["cost"]["spent"] == 90
    output = Path(summary["output_path"])
    assert output.exists()
    assert await is_playable(output)
    await resumed_worker.aclose()


@pytest.mark.asyncio
async def test_zero_capacity_falls_back_in_same_ordered_slots_and_completes(tmp_path: Path) -> None:
    """P0 #0: no router capacity is a local Ken-Burns/synthetic render path, not a stall."""
    backend = MockVideoBackend(MockVideoConfig(seats=[]))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(
        script="A long mock production.", target_seconds=25, admission_mode="waves"
    ))
    assert admitted["accepted"]
    assert admitted["film"]["status"] == "admitted"
    assert admitted["shortfall"] > 0
    film_id = admitted["film"]["id"]
    outcome = await pipeline.tick(film_id)
    summary = pipeline.store.summary(film_id)
    assert outcome["actions"]["fallback_capacity"] == summary["unique_jobs"]
    assert len(backend.jobs_by_key) == 0
    assert summary["status"] == "completed"
    assert summary["job_states"] == {"succeeded": summary["unique_jobs"]}
    assert summary["cost"]["fallback_jobs"] == summary["unique_jobs"]
    assert Path(summary["output_path"]).exists()
    assert await is_playable(Path(summary["output_path"]))
    await pipeline.aclose()


class _SlateOnlyFallback:
    """A deliberate image-supply failure used to prove slate finalization policy."""

    async def materialize_fallback(
        self, *, destination: Path, duration_seconds: int, aspect_ratio: str, **_: object
    ) -> FallbackMaterialization:
        await media.synthesize_slate_clip(destination, duration=duration_seconds, width=64, height=36)
        return FallbackMaterialization(destination, "slate", "simulated image provider 429")


def _slate_pipeline(tmp_path: Path, backend: MockVideoBackend) -> FilmOrchestrator:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://mock-video")
    return FilmOrchestrator(
        store=FilmJobStore(tmp_path / "film_jobs.sqlite3"), chat=DeterministicMockChatClient(),
        video=VideoRouterClient(client=http), artifact_root=tmp_path / "artifacts",
        materializer=SyntheticClipMaterializer(width=64, height=36),
        fallback_materializer=_SlateOnlyFallback(), segment_size=2,
    )


@pytest.mark.asyncio
async def test_slate_heavy_cut_is_visible_and_cannot_finalize_without_explicit_approval(tmp_path: Path) -> None:
    backend = MockVideoBackend(MockVideoConfig(seats=[]))
    pipeline = _slate_pipeline(tmp_path, backend)
    request = FilmRequest(script="A slate quality policy test.", target_seconds=10, with_audio=False)
    admitted = await pipeline.request_film(request)
    film_id = admitted["film"]["id"]

    blocked = await pipeline.tick(film_id)
    summary = blocked["film"]
    assert summary["status"] == "quality_blocked_slates"
    assert summary["cost"]["slate_logical_shots"] == summary["logical_shots"] == 2
    assert summary["cost"]["slate_fraction"] == 1.0
    assert summary["output_path"] is None
    assert "refusing final MP4" in summary["last_error"]

    replay = await pipeline.request_film(FilmRequest(
        script=request.script, target_seconds=request.target_seconds, with_audio=False, allow_slates=True,
    ))
    assert replay["idempotent_replay"] is True
    completed = await pipeline.tick(film_id)
    assert completed["film"]["status"] == "completed"
    assert Path(completed["film"]["output_path"]).exists()
    await pipeline.aclose()


def test_planner_json_is_strict_and_does_not_recover_embedded_fragments() -> None:
    with pytest.raises(ValueError, match="router contract failure"):
        _extract_json("Here is the JSON you requested:\n[{\"prompt\": \"not accepted\"}]")


@pytest.mark.asyncio
async def test_scene_shared_stills_have_six_distinct_camera_moves() -> None:
    planner = ShotListPlanner(DeterministicMockChatClient())
    shots = await planner.decompose(
        "A photographer follows the river at dusk.", target_seconds=30,
        bible={"style": "cinematic", "imageRefs": []}, seed=71,
    )
    assert len(shots) == 6
    scene = [shot.continuity["shot"] for shot in shots]
    assert {str(item["stillPrompt"]) for item in scene} == {"mock scene 1, stable protagonist and location"}
    assert len({str(item["cameraMove"]).casefold() for item in scene}) == 6
    assert {item["stillSeed"] for item in scene} == {71}
    assert shots[0].hero_shot is True


@pytest.mark.asyncio
async def test_approved_character_references_are_persisted_and_relayed_to_every_shot(tmp_path: Path) -> None:
    backend = MockVideoBackend(MockVideoConfig(seats=[]))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(
        script="Mara crosses the observatory in a storm.", target_seconds=10,
        image_refs=["https://assets.example/background.jpg"],
        character_refs={
            "mara": {
                "sheetUrl": "https://assets.example/mara-sheet.jpg",
                "portraitUrls": ["https://assets.example/mara-front.jpg", "https://assets.example/mara-profile.jpg"],
            }
        },
        with_audio=False,
    ))
    film_id = admitted["film"]["id"]
    expected = [
        "https://assets.example/background.jpg",
        "https://assets.example/mara-sheet.jpg",
        "https://assets.example/mara-front.jpg",
        "https://assets.example/mara-profile.jpg",
    ]
    film = pipeline.store.get_film(film_id)
    assert film["bible"]["characterRefs"] == {"mara": expected[1:]}
    assert film["bible"]["imageRefs"] == expected
    assert all(shot["image_refs"] == expected for shot in pipeline.store.shots(film_id))
    await pipeline.aclose()


class _MalformedPlannerChat:
    async def aclose(self) -> None:
        return None

    async def message(self, *_: object, **__: object) -> ChatReply:
        return ChatReply(text="not-json", provider="broken-json-seat")


@pytest.mark.asyncio
async def test_planner_contract_error_names_the_provider_without_relaxing_json() -> None:
    planner = ShotListPlanner(_MalformedPlannerChat())
    with pytest.raises(ValueError, match="broken-json-seat"):
        await planner.create_bible("A strict planner diagnostics test.")


@pytest.mark.asyncio
async def test_still_cache_uses_scene_identity_and_reuses_retained_art_after_429(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    materializer = KenBurnsFallbackMaterializer(width=64, height=36, still_request_gap_seconds=0)
    fetches: list[str] = []

    async def fake_download(url: str, dest: Path, **_: object) -> Path:
        fetches.append(url)
        if len(fetches) == 2:
            raise media.MediaContentTypeError("expected image/ response, got HTTP 429 content-type application/json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"image" * 300)
        return dest

    async def fake_kenburns(still: Path, dest: Path, **_: object) -> Path:
        assert still.exists()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"mp4")
        return dest

    monkeypatch.setattr("film_pipeline.assembly.media.download", fake_download)
    monkeypatch.setattr("film_pipeline.assembly.media.synthesize_kenburns_clip", fake_kenburns)

    async def render_scene(scene: int) -> list[FallbackMaterialization]:
        return [
            await materializer.materialize_fallback(
                prompt=f"unique moving prompt {scene}/{shot}", image_refs=[], seed=1000 + shot,
                continuity={"shot": {
                    "stillPrompt": f"scene still {scene}", "stillSeed": 500 + scene,
                    "cameraMove": f"move {shot}",
                }},
                destination=tmp_path / "film" / "clips" / f"scene-{scene}-shot-{shot}.mp4",
                duration_seconds=5, aspect_ratio="16:9",
            )
            for shot in range(6)
        ]

    first = await render_scene(1)
    second = await render_scene(2)
    third = await render_scene(3)
    # Six variants of scene 1 cost one image fetch.  Scene 2 detects the non-image
    # rate-limit response, and scene 3 makes no further request: it reuses scene 1.
    assert len(fetches) == 2
    assert all(item.kind == "kenburns" for item in first + second + third)
    assert any(item.detail and "image supply stopped" in item.detail for item in second + third)


@pytest.mark.asyncio
async def test_non_image_download_response_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def responder(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"content-type": "application/json"}, content=b'{"error":"queued"}')

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    with pytest.raises(media.MediaContentTypeError):
        await media.download(
            "http://image.test/still", tmp_path / "still.jpg", client=client,
            attempts=3, expected_content_type_prefix="image/",
        )
    await client.aclose()
    assert calls == 1


class _CountingFallback:
    def __init__(self) -> None:
        self.indices: list[int] = []

    async def materialize_fallback(self, *, prompt: str, destination: Path, **_: object) -> FallbackMaterialization:
        self.indices.append(int(prompt.rsplit(" ", 1)[-1]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"clip")
        return FallbackMaterialization(destination, "kenburns")


@pytest.mark.asyncio
async def test_resume_after_200_of_360_only_materializes_remaining_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A durable worker restart must never re-render already materialized coverage."""
    async def fake_playable(path: Path) -> bool:
        return Path(path).exists()

    async def fake_concat(_: object, dest: Path, **__: object) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"segment")
        return dest

    async def fake_mix(_: Path, dest: Path, **__: object) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"film")
        return dest

    monkeypatch.setattr(media, "is_playable", fake_playable)
    monkeypatch.setattr(media, "concat_copy", fake_concat)
    monkeypatch.setattr(media, "mix_final_audio", fake_mix)

    store = FilmJobStore(tmp_path / "film_jobs.sqlite3")
    film = store.create_film(
        request_key="resume-200-of-360", script="Resume durability proof.", target_seconds=1800,
        aspect_ratio="16:9", bible={"style": "test", "imageRefs": []}, status="admitted",
        admission_mode="waves", capacity_at_admission=0,
    )
    shots = [ShotSpec(index=index, prompt=f"resume prompt {index}", canonical_index=index) for index in range(360)]
    job_keys = {index: f"resume-job-{index}" for index in range(360)}
    store.add_shots_and_jobs(film["id"], shots, aspect_ratio="16:9", job_keys=job_keys)
    artifact_root = tmp_path / "artifacts"
    # This simulates the durable checkpoint immediately before a worker crash.
    from film_pipeline.assembly import IncrementalAssembler
    pre_crash_assembler = IncrementalAssembler(store, artifact_root, segment_size=60)
    for index in range(200):
        path = pre_crash_assembler.clip_path(film["id"], job_keys[index])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"already-rendered")
        store.mark_fallback_success(job_keys[index], str(path), kind="kenburns")
    for index in range(200, 360):
        store.mark_fallback_pending(job_keys[index], "simulated worker crash after slot 200")
    assert await pre_crash_assembler.assemble_available(film["id"]) is None
    assert len(store.segments(film["id"])) == 3

    backend = MockVideoBackend(MockVideoConfig(seats=[]))
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://mock-video")
    fallback = _CountingFallback()
    resumed = FilmOrchestrator(
        store=store, chat=DeterministicMockChatClient(), video=VideoRouterClient(client=http),
        artifact_root=artifact_root, materializer=SyntheticClipMaterializer(width=64, height=36),
        fallback_materializer=fallback, segment_size=60,
    )

    async def no_soundtrack(*_: object, **__: object) -> None:
        return None

    resumed._configure_soundtrack = no_soundtrack  # type: ignore[method-assign]
    outcome = await resumed.tick(film["id"])
    assert fallback.indices == list(range(200, 360))
    assert outcome["film"]["status"] == "completed"
    assert len(store.segments(film["id"])) == 6
    assert Path(outcome["film"]["output_path"]).exists()
    await resumed.aclose()


@pytest.mark.asyncio
async def test_transient_and_wall_failures_have_distinct_safe_states(tmp_path: Path) -> None:
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=4)]))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(script="A failure classification test.", target_seconds=10))
    film_id = admitted["film"]["id"]
    jobs = pipeline.store.jobs_for_film(film_id)
    backend.config.submit_transient_failures[jobs[0]["job_key"]] = 1
    backend.config.terminal_failures[jobs[1]["job_key"]] = "wall: phone verification required"

    await pipeline.tick(film_id)
    transient = pipeline.store.get_job(jobs[0]["job_key"])
    assert transient["status"] == "retry_wait"
    assert transient["attempts"] == 1

    # Advance only the retry clock in durable state; this is not an upstream retry loop.
    pipeline.store.defer(jobs[0]["job_key"], status="pending", seconds=0, error="test resume")
    for _ in range(5):
        await pipeline.tick(film_id)
    wall = pipeline.store.get_job(jobs[1]["job_key"])
    assert wall["status"] == "succeeded"
    assert wall["is_fallback"] == 1
    assert pipeline.store.summary(film_id)["status"] == "completed"
    await pipeline.aclose()


def test_dedup_only_reuses_byte_identical_render_payloads() -> None:
    """P0 #2/#3: position seeds do not defeat reuse, and actions never fuzzy-merge."""
    shots = deduplicate_shots([
        ShotSpec(index=0, prompt="A hits B", image_refs=["https://ref/a.png"], seed=11),
        ShotSpec(index=1, prompt="A hits B", image_refs=["https://ref/a.png"], seed=99),
        ShotSpec(index=2, prompt="B hits A", image_refs=["https://ref/a.png"], seed=11),
        ShotSpec(index=3, prompt="A hits B", image_refs=["https://ref/b.png", "https://ref/a.png"], seed=11),
    ])
    assert [shot.canonical_index for shot in shots] == [0, 0, 2, 3]
    assert shots[1].seed == 11


@pytest.mark.asyncio
async def test_zero_shot_idempotent_replay_recovers_crash_window(tmp_path: Path) -> None:
    """P0 #5: a row created before process death is planned on replay, not bricked."""
    backend = MockVideoBackend(MockVideoConfig(seats=[]))
    pipeline = _pipeline(tmp_path, backend)
    request = FilmRequest(script="Recover the interrupted plan.", target_seconds=10, with_audio=False)
    bible = {"style": "cinematic", "imageRefs": []}
    key = request_key_for_film(
        script=request.script, target_seconds=request.target_seconds, aspect_ratio=request.aspect_ratio,
        bible=bible, seed=request.seed,
    )
    stranded = pipeline.store.create_film(
        request_key=key, script=request.script, target_seconds=request.target_seconds,
        aspect_ratio=request.aspect_ratio, bible=bible, status="admitted", admission_mode="refuse",
        capacity_at_admission=0,
    )
    assert stranded["logical_shots"] == 0
    recovered = await pipeline.request_film(FilmRequest(
        script=request.script, target_seconds=10, bible=bible, with_audio=False,
    ))
    assert recovered["accepted"]
    assert recovered["film"]["id"] == stranded["id"]
    assert recovered["film"]["logical_shots"] == 2
    await pipeline.aclose()


@pytest.mark.asyncio
async def test_concurrent_ticks_claim_once_before_router_submit(tmp_path: Path) -> None:
    """P0 #4: two workers/ticks cannot make two billable POSTs for one durable job."""
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=1)]))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(script="One atomic claim.", target_seconds=5))
    film_id = admitted["film"]["id"]
    await asyncio.gather(pipeline.tick(film_id), pipeline.tick(film_id))
    assert len(backend.jobs_by_key) == 1
    job = pipeline.store.jobs_for_film(film_id)[0]
    assert job["attempts"] == 1
    assert job["status"] in {"queued", "running", "succeeded"}
    await pipeline.aclose()


@pytest.mark.asyncio
async def test_distinct_provider_lanes_submit_in_parallel_in_one_tick(tmp_path: Path) -> None:
    """§4.3: three independent provider lanes become three queued router jobs at once."""
    backend = MockVideoBackend(MockVideoConfig(
        latency_seconds=60,
        seats=[
            MockSeat("seat-a", provider="provider-a", clips_remaining=1),
            MockSeat("seat-b", provider="provider-b", clips_remaining=1),
            MockSeat("seat-c", provider="provider-c", clips_remaining=1),
        ],
    ))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(script="Three independent lanes.", target_seconds=15))
    outcome = await pipeline.tick(admitted["film"]["id"])
    assert outcome["actions"]["submitted"] == 3
    assert len(backend.jobs_by_key) == 3
    assert pipeline.store.summary(admitted["film"]["id"])["job_states"] == {"queued": 3}
    await pipeline.aclose()


@pytest.mark.asyncio
async def test_permanent_transient_failure_marks_film_terminal_failed(tmp_path: Path) -> None:
    """P0 #1: a permanently dead non-fallback job cannot be relabelled running."""
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=1)]))
    pipeline = _pipeline(tmp_path, backend)
    pipeline.max_attempts = 1
    admitted = await pipeline.request_film(FilmRequest(script="Terminal failure.", target_seconds=5))
    film_id = admitted["film"]["id"]
    key = pipeline.store.jobs_for_film(film_id)[0]["job_key"]
    backend.config.submit_transient_failures[key] = 1
    first = await pipeline.tick(film_id)
    assert first["film"]["status"] == "failed"
    assert pipeline.store.get_job(key)["status"] == "quarantined"
    second = await pipeline.tick(film_id)
    assert second["film"]["status"] == "failed"
    assert second["actions"] == {"terminal": 1}
    await pipeline.aclose()


@pytest.mark.asyncio
async def test_auth_isolated_to_failed_seat_and_slot_completes_locally(tmp_path: Path) -> None:
    """P1 #6: auth failure parks the actual assigned seat, never the whole router."""
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=1)]))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(script="Auth failure.", target_seconds=5))
    film_id = admitted["film"]["id"]
    key = pipeline.store.jobs_for_film(film_id)[0]["job_key"]
    backend.config.terminal_failures[key] = "auth: session expired"
    await pipeline.tick(film_id)
    second = await pipeline.tick(film_id)
    assert ("seat-a", "mock-video") in pipeline.store.unavailable_seats()
    assert pipeline.store.get_job(key)["is_fallback"] == 1
    assert second["film"]["status"] == "completed"
    await pipeline.aclose()


@pytest.mark.asyncio
async def test_poll_and_capacity_non_2xx_never_crash_or_charge_attempts(tmp_path: Path) -> None:
    """P1 #7/#8: HTTP errors are isolated and a failed poll is not a render failure."""
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=2)]))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(script="Transport resilience.", target_seconds=5))
    film_id = admitted["film"]["id"]
    key = pipeline.store.jobs_for_film(film_id)[0]["job_key"]
    await pipeline.tick(film_id)
    backend.config.poll_http_failures[key] = [404]
    polled = await pipeline.tick(film_id)
    job = pipeline.store.get_job(key)
    assert polled["actions"]["poll_errors"] == 1
    assert job["attempts"] == 1
    assert job["status"] == "queued"

    # Create a second independent film so a bad capacity read is exercised before a
    # pending job can submit. It must return a normal scheduler response, not a 502.
    second = await pipeline.request_film(FilmRequest(script="Capacity endpoint resilience.", target_seconds=5))
    backend.config.capacity_http_failures[:] = [403]
    resilient = await pipeline.tick(second["film"]["id"])
    assert resilient["actions"]["capacity_errors"] == 1
    assert resilient["film"]["status"] in {"admitted", "running"}
    await pipeline.aclose()


@pytest.mark.asyncio
async def test_refused_safety_cap_is_terminal_and_360_shot_graph_resumes(tmp_path: Path) -> None:
    """P1 #9 plus §4.3: refusal remains terminal; 30 minutes plans exactly 360 shots."""
    backend = MockVideoBackend(MockVideoConfig(seats=[]))
    pipeline = _pipeline(tmp_path, backend)
    refused = await pipeline.request_film(FilmRequest(
        script="Deliberately refuse paid motion.", target_seconds=15, max_clips=1,
        allow_fallback=False, with_audio=False,
    ))
    assert refused["film"]["status"] == "refused_safety_cap"
    after_tick = await pipeline.tick(refused["film"]["id"])
    assert after_tick["film"]["status"] == "refused_safety_cap"

    long_request = FilmRequest(script="Thirty-minute scale proof.", target_seconds=1_800, with_audio=False)
    planned = await pipeline.request_film(long_request)
    assert planned["logical_shots"] == 360
    assert planned["film"]["logical_shots"] == 360
    await pipeline.aclose()

    resumed = _pipeline(tmp_path, backend)
    replay = await resumed.request_film(long_request)
    assert replay["idempotent_replay"] is True
    assert replay["film"]["logical_shots"] == 360
    assert replay["film"]["unique_jobs"] == planned["film"]["unique_jobs"]
    await resumed.aclose()


def test_film_api_mock_e2e_and_live_safety_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The public FastAPI workflow reaches a final playable container without a router."""
    from app.api.v1.endpoints import films
    from app.main import app

    monkeypatch.setenv("FILM_PIPELINE_STORAGE_PATH", str(tmp_path / "api-store"))
    # Rebuild the singleton after setting its storage value; production keeps one per process.
    films._services = films._ServicePool()
    with TestClient(app) as client:
        refused_live = client.post("/api/v1/films/", json={
            "script": "This must not spend credits.", "backend": "live", "live": False, "max_clips": 0,
        })
        assert refused_live.status_code == 400

        created = client.post("/api/v1/films/", json={
            "script": "A courier crosses a moonlit bridge.", "target_seconds": 15,
        })
        assert created.status_code == 200
        film_id = created.json()["film"]["id"]
        latest = None
        for _ in range(6):
            latest = client.post(f"/api/v1/films/{film_id}/tick")
            assert latest.status_code == 200
            if latest.json()["film"]["status"] == "completed":
                break
        assert latest.json()["film"]["status"] == "completed"
        readback = client.get(f"/api/v1/films/{film_id}")
        assert readback.status_code == 200
        assert Path(readback.json()["output_path"]).exists()
