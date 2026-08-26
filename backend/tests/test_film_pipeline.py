"""Zero-credit integration tests for the durable film consumption pipeline."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from film_pipeline.assembly import SyntheticClipMaterializer
from film_pipeline.clients import VideoNoCapacity, VideoRouterClient
from film_pipeline.mock import DeterministicMockChatClient, MockSeat, MockVideoBackend, MockVideoConfig
from film_pipeline.orchestrator import FilmOrchestrator, FilmRequest
from film_pipeline.store import FilmJobStore
from studio_pipeline.media import is_playable


def _pipeline(tmp_path: Path, backend: MockVideoBackend) -> FilmOrchestrator:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://mock-video")
    return FilmOrchestrator(
        store=FilmJobStore(tmp_path / "film_jobs.sqlite3"), chat=DeterministicMockChatClient(),
        video=VideoRouterClient(client=http), artifact_root=tmp_path / "artifacts",
        materializer=SyntheticClipMaterializer(width=64, height=36), segment_size=2,
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
async def test_capacity_shortfall_wave_parks_without_a_tight_retry_loop(tmp_path: Path) -> None:
    backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("seat-a", clips_remaining=1)]))
    pipeline = _pipeline(tmp_path, backend)
    admitted = await pipeline.request_film(FilmRequest(
        script="A long mock production.", target_seconds=25, admission_mode="waves"
    ))
    assert admitted["accepted"]
    assert admitted["film"]["status"] == "wave_scheduled"
    assert admitted["shortfall"] > 0
    film_id = admitted["film"]["id"]
    await pipeline.tick(film_id)
    await pipeline.tick(film_id)
    summary = pipeline.store.summary(film_id)
    assert len(backend.jobs_by_key) == 1
    assert summary["job_states"].get("parked_capacity", 0) >= 1
    parked = [job for job in pipeline.store.jobs_for_film(film_id) if job["status"] == "parked_capacity"]
    assert all(job["next_attempt_at"] > job["updated_at"] for job in parked)
    await pipeline.aclose()


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
    assert wall["status"] == "parked_wall"
    assert ("seat-a", "mock-video") in pipeline.store.unavailable_seats()
    await pipeline.aclose()


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
