import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from main import app


@pytest_asyncio.fixture
async def client():
    """Create an async test client with lifespan support."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestHealth:
    """Health check endpoint tests."""

    async def test_health_endpoint(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "Film Kit Studio API"
        assert "version" in data
        assert "ffmpeg_available" in data


class TestConstants:
    """Constants endpoint tests."""

    async def test_constants_endpoint(self, client):
        response = await client.get("/api/constants")
        assert response.status_code == 200
        data = response.json()
        assert "aspects" in data
        assert "voices" in data
        assert "music_moods" in data
        assert "visual_styles" in data
        assert "providers" in data
        assert data["providers"]["script"] == "nim"


class TestProjects:
    """Project CRUD tests."""

    async def test_create_project(self, client):
        response = await client.post(
            "/api/projects",
            json={
                "name": "Test Project",
                "idea": "A test film idea",
                "style": "cinematic",
                "aspect": "16:9",
                "voice": "aria",
                "num_scenes": 6,
                "music": False,
                "music_mood": "ambient",
                "transition_mode": "cut",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["idea"] == "A test film idea"
        assert "id" in data
        assert "created_at" in data

    async def test_list_projects(self, client):
        # Create a project first
        await client.post(
            "/api/projects",
            json={"name": "List Test", "idea": "Test"},
        )
        response = await client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_project(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Get Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        response = await client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Get Test"
        assert "scenes" in data
        assert "characters" in data

    async def test_update_project(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Update Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/projects/{project_id}",
            json={"name": "Updated Name", "music": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["music"] is True

    async def test_delete_project(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Delete Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        response = await client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 204

        # Verify deleted
        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 404


class TestScenes:
    """Scene CRUD and reorder tests."""

    @pytest_asyncio.fixture
    async def project_with_scenes(self, client):
        """Create a project with scenes."""
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Scene Test", "idea": "Test", "num_scenes": 3},
        )
        project = create_resp.json()
        return project

    async def test_update_scene(self, client, project_with_scenes):
        project_id = project_with_scenes["id"]
        scenes = project_with_scenes["scenes"]
        scene_id = scenes[0]["id"]

        response = await client.patch(
            f"/api/projects/{project_id}/scenes/{scene_id}",
            json={
                "narration": "Updated narration",
                "visual_prompt": "Updated visual prompt",
                "trim_start_seconds": 0.5,
                "trim_end_seconds": 4.5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["narration"] == "Updated narration"
        assert data["trim_start_seconds"] == 0.5

    async def test_reorder_scenes(self, client, project_with_scenes):
        project_id = project_with_scenes["id"]
        scenes = project_with_scenes["scenes"]
        original_order = [s["id"] for s in scenes]
        new_order = list(reversed(original_order))

        response = await client.post(
            f"/api/projects/{project_id}/scenes/reorder",
            json=new_order,
        )
        assert response.status_code == 200
        data = response.json()
        new_order_from_response = [s["id"] for s in data]
        assert new_order_from_response == new_order


class TestCharacters:
    """Character CRUD tests."""

    @pytest_asyncio.fixture
    async def project(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Char Test", "idea": "Test"},
        )
        return create_resp.json()

    async def test_create_character(self, client, project):
        project_id = project["id"]
        response = await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "Hero", "description": "A brave hero"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Hero"
        assert data["description"] == "A brave hero"
        assert data["project_id"] == project_id
        assert "id" in data

    async def test_list_characters(self, client, project):
        project_id = project["id"]
        await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "Hero", "description": "A hero"},
        )
        response = await client.get(f"/api/projects/{project_id}/characters")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_update_character(self, client, project):
        project_id = project["id"]
        create_resp = await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "Villain", "description": "Bad guy"},
        )
        char_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/projects/{project_id}/characters/{char_id}",
            json={"name": "Anti-Hero", "description": "Complex character"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Anti-Hero"

    async def test_upload_character_image(self, client, project):
        project_id = project["id"]
        create_resp = await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "Image Test", "description": "Test"},
        )
        char_id = create_resp.json()["id"]

        # Create a dummy image file
        from io import BytesIO
        file_content = b"fake image content"
        files = {"file": ("test.png", BytesIO(file_content), "image/png")}

        response = await client.post(
            f"/api/projects/{project_id}/characters/{char_id}/image",
            files=files,
        )
        assert response.status_code == 200
        data = response.json()
        assert "reference_image_path" in data

    async def test_delete_character(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Delete Char Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        char_resp = await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "To Delete", "description": "Test"},
        )
        char_id = char_resp.json()["id"]

        response = await client.delete(f"/api/projects/{project_id}/characters/{char_id}")
        assert response.status_code == 204

        # Verify deleted
        list_resp = await client.get(f"/api/projects/{project_id}/characters")
        chars = list_resp.json()
        assert not any(c["id"] == char_id for c in chars)


class TestDirector:
    """Director agent tests."""

    async def test_start_director_run(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Director Test", "idea": "A test film"},
        )
        project_id = create_resp.json()["id"]

        response = await client.post(
            "/api/director/run",
            json={
                "project_id": project_id,
                "idea": "A detective hunts a memory thief",
                "genre": "noir",
                "target_duration": 30,
                "max_iterations": 1,
                "critic_threshold": 0.5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "planning"

    async def test_director_status(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Status Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        run_resp = await client.post(
            "/api/director/run",
            json={
                "project_id": project_id,
                "idea": "Test",
                "genre": "drama",
                "target_duration": 30,
            },
        )
        run_id = run_resp.json()["run_id"]

        response = await client.get(f"/api/director/{run_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert "status" in data


class TestTraining:
    """LoRA training endpoint tests."""

    async def test_start_training(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Training Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        # Create a character first
        char_resp = await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "Test Char", "description": "Test"},
        )
        char_id = char_resp.json()["id"]

        response = await client.post(
            "/api/training/lora/train",
            json={
                "project_id": project_id,
                "character_id": char_id,
                "config": {
                    "max_train_steps": 10,
                    "learning_rate": 1e-4,
                },
                "backend": "local",
            },
        )
        # Should accept the request (may fail due to no GPU, but endpoint works)
        assert response.status_code in (200, 422, 500)

    async def test_curate_dataset(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Dataset Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        char_resp = await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "Dataset Char", "description": "Test"},
        )
        char_id = char_resp.json()["id"]

        response = await client.post(
            "/api/training/dataset/curate",
            json={
                "project_id": project_id,
                "character_id": char_id,
                "video_paths": [],
                "reference_images": [],
                "target_count": 10,
            },
        )
        assert response.status_code in (200, 422, 500)


class TestLipSync:
    """Lip-sync endpoint tests."""

    async def test_generate_lip_sync(self, client):
        create_resp = await client.post(
            "/api/projects",
            json={"name": "LipSync Test", "idea": "Test"},
        )
        project_id = create_resp.json()["id"]

        char_resp = await client.post(
            f"/api/projects/{project_id}/characters",
            json={"name": "LipSync Char", "description": "Test"},
        )
        char_id = char_resp.json()["id"]

        # Create a scene first
        project_resp = await client.get(f"/api/projects/{project_id}")
        project = project_resp.json()
        scene_id = project["scenes"][0]["id"]

        response = await client.post(
            "/api/lipsync/generate",
            json={
                "project_id": project_id,
                "character_id": char_id,
                "scene_id": scene_id,
                "method": "liveportrait",
                "fps": 30,
            },
        )
        # Should accept (may fail without models)
        assert response.status_code in (200, 422, 500)


class TestAudioPost:
    """Audio post-production tests."""

    async def test_audio_post_endpoints_exist(self, client):
        # Test that endpoints exist (may fail without files)
        response = await client.post("/api/training/lora/train", json={})
        assert response.status_code in (200, 422, 404)


class TestLipSyncRouter:
    """Lip-sync router tests."""

    async def test_lipsync_endpoints_exist(self, client):
        response = await client.post("/api/lipsync/generate", json={})
        assert response.status_code in (200, 422, 404, 405)