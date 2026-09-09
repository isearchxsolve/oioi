import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.v1.dependencies.auth import get_current_user
from app.models.user import User
from app.api.v1.endpoints import films as films_endpoint
from studio_pipeline.omniroute import OmniRouteClient, OmniRouteError
from providers.registry import get_registry, reset_registry
from providers.base import (
    AIProviderAdapter,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    ProviderHealth,
    ProviderStatus,
    Model,
)


# One JSON payload per crew role. A single union object cannot work: `characters` is List[str] on
# ScriptwriterOutput but List[Dict[str, Any]] on CharacterDesignerOutput, and `sound_effects` is
# List[Dict], so the same key means different types to different agents. Each agent is identified by
# the "You are a <role>" line the orchestrator puts in its system prompt.
MOCK_AGENT_JSON = {
    "Scriptwriter": {
        "title": "Mock Film",
        "description": "A robot finds a glowing blue flower on a dystopian planet.",
        "scenes": [
            {"prompt": "The robot crosses the ash plain at dusk", "duration": 5},
            {"prompt": "It kneels before the glowing flower", "duration": 5},
        ],
        "characters": ["Unit-7, a rusted scout robot"],
    },
    "Art Director": {
        "visual_style": "cyberpunk anime",
        "color_palette": ["#0FF0FC", "#FF00A0", "#101014"],
        "character_sheet_prompt": "rusted scout robot, full body turnaround",
        "scene_style_prompt": "dystopian ash plain, neon rim light",
    },
    "Character Designer": {
        "characters": [
            {"name": "Unit-7", "description": "a rusted scout robot",
             "prompt": "rusted scout robot, chipped paint, single blue optic"},
        ],
    },
    "Scene Designer": {
        "scenes": [
            {"description": "ash plain at dusk", "prompt": "wide ash plain, low sun",
             "style": "cyberpunk anime"},
            {"description": "crater with flower", "prompt": "crater, glowing blue flower",
             "style": "cyberpunk anime"},
        ],
    },
    "Storyboard Artist": {
        "panels": [
            {"scene": 1, "shot": "wide establishing", "composition": "robot small, frame left",
             "camera": "slow pan right", "action": "Unit-7 crosses the ash plain"},
            {"scene": 2, "shot": "close up", "composition": "flower centred, robot hands enter",
             "camera": "slow push in", "action": "Unit-7 kneels before the flower"},
        ],
    },
    "Animator": {
        "animations": [
            {"scene": 1, "motion": "Pan",
             "prompt": "a slow camera pan across an ash plain at dusk as a rusted robot walks",
             "duration": 5},
            {"scene": 2, "motion": "Push in",
             "prompt": "a slow push in on a glowing blue flower in a crater as dust drifts past",
             "duration": 5},
        ],
    },
    "Sound Director": {
        "music_prompt": "synthwave ambient pulse, 120 BPM",
        "sound_effects": [{"scene": 1, "sfx": "Wind"}, {"scene": 2, "sfx": "Servo whine"}],
        "voice_over": "The journey begins.",
    },
    "Director": {
        "final_notes": "Approved for final cut.",
        "approved": True,
        "revisions": [],
    },
}

# Longest first: "Character Designer" and "Scene Designer" both contain "Designer", and every role
# line would match a bare "Director" substring check.
_ROLE_ORDER = [
    "Scriptwriter", "Art Director", "Character Designer", "Scene Designer",
    "Storyboard Artist", "Animator", "Sound Director", "Director",
]


def _mock_agent_payload(messages) -> dict:
    system = ""
    for m in messages or []:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        if role == "system":
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            system = content or ""
            break
    for role_name in _ROLE_ORDER:
        if f"You are a {role_name}" in system or f"You are an {role_name}" in system \
                or f"You are an expert {role_name}" in system:
            return MOCK_AGENT_JSON[role_name]
    return MOCK_AGENT_JSON["Director"]


class MockChatAdapter(AIProviderAdapter):
    def __init__(self, name: str = "mock_chat"):
        self.provider_name = name
        self.health_status = ProviderStatus.HEALTHY

    def get_provider_name(self) -> str:
        return self.provider_name

    async def chat_completion(self, request=None, *args, **kwargs):
        # Returns ChatCompletionResponse, not a bare dict. The orchestrator reads every agent
        # response as `response.choices[0]["message"]["content"]` then json.loads it, so the old
        # dict return raised `'dict' object has no attribute 'choices'` and its prose content
        # would have failed _parse_json immediately after.
        import json as _json
        messages = getattr(request, "messages", None) if request is not None else None
        payload = _mock_agent_payload(messages)
        return ChatCompletionResponse(
            id="mock-1",
            model="mock-model",
            choices=[{
                "index": 0,
                "message": {"role": "assistant", "content": _json.dumps(payload)},
                "finish_reason": "stop",
            }],
            usage={"total_tokens": 42},
        )

    async def chat_completion_stream(self, *args, **kwargs):
        async def gen():
            yield ChatCompletionResponse(
                id="mock-id",
                model="mock",
                choices=[{"index": 0, "message": {"role": "assistant", "content": "streamed"}, "finish_reason": "stop"}],
                usage={},
            )
        return gen()

    async def generate_image(self, *args, **kwargs):
        return "https://image.pollinations.ai/prompt/cyberpunk%20city"

    async def generate_video(self, *args, **kwargs):
        # Returns the real contract -- VideoGenerationResponse, not a bare URL string. The old
        # version returned a str, which matched the endpoint's old (broken) call and nothing else:
        # every adapter in providers/ is declared as generate_video(request) -> VideoGenerationResponse.
        return VideoGenerationResponse(
            data=[{"url": "https://cdn.pollinations.ai/video/clip_scene_1.mp4",
                   "credits_charged": 0}]
        )

    async def create_embedding(self, *args, **kwargs):
        from providers.base import EmbeddingResponse
        return EmbeddingResponse(object="list", data=[], model="mock-embed", usage={})

    async def list_models(self):
        return [Model(id="mock-model", object="model")]

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="mock_chat", status=ProviderStatus.HEALTHY)


@pytest.fixture(autouse=True)
def setup_mock_registry():
    reset_registry()
    registry = get_registry()
    # priority=-1, not 0, and that matters for money. init_registry() runs on every request and
    # registers the real providers from settings.PROVIDER_PRIORITY, where omniroute_video sits at
    # index 0 -- and omniroute_video spends real Flow/rtst credits per clip. At equal priority the
    # winner would be decided by dict insertion order, so a test run could submit a genuine
    # 20-credit job. A negative priority makes the mock unbeatable here by construction.
    registry.register("mock_chat", MockChatAdapter(), priority=-1, capabilities=("chat", "image", "video", "audio"))
    yield
    reset_registry()


@pytest.fixture(autouse=True)
def authenticated_api_principal():
    """Legacy endpoint contract tests exercise behavior after authentication."""
    app.dependency_overrides[get_current_user] = lambda: User(
        id="test-api-owner", email="test-api-owner@example.test", is_active=True, is_superuser=True
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "providers" in data
    assert "nim" not in data  # NVIDIA removed per AC-10


def test_chat_completion_uses_the_canonical_consumer(monkeypatch):
    from app.api.v1.endpoints import chat as chat_endpoint

    class FakeConsumerChat:
        async def message(self, content, *, max_tokens, model):
            assert model == "session-pool/auto"
            return SimpleNamespace(text="A canonical reply", provider="gateway", session="seat-1", tenant="tenant")

        async def aclose(self):
            return None

    monkeypatch.setattr(chat_endpoint, "ChatPoolClient", lambda: FakeConsumerChat())
    client = TestClient(app)
    payload = {
        "messages": [{"role": "user", "content": "Write a script for cyberpunk samurai"}],
        "model": "gemini-2.5-flash",
    }
    response = client.post("/api/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "A canonical reply"
    assert data["provider"] == "gateway"


def test_chat_stream_uses_the_canonical_consumer(monkeypatch):
    from app.api.v1.endpoints import chat as chat_endpoint

    class FakeConsumerChat:
        async def message(self, content, *, max_tokens, model):
            return SimpleNamespace(text="A canonical reply", provider="gateway", session="seat-1", tenant="tenant")

        async def aclose(self):
            return None

    monkeypatch.setattr(chat_endpoint, "ChatPoolClient", lambda: FakeConsumerChat())
    client = TestClient(app)
    response = client.get("/api/v1/chat/stream?prompt=Hello")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


def test_direct_image_generation_endpoint_is_retired():
    client = TestClient(app)
    payload = {
        "prompt": "Cyberpunk cityscape neon rain",
        "style": "Anime",
    }
    response = client.post("/api/v1/images/generations", json=payload)
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "legacy_route_retired"


def test_videos_generations_endpoint():
    client = TestClient(app)
    payload = {
        "prompt": "Camera panning across cyberpunk skyscrapers",
    }
    response = client.post("/api/v1/videos/generations", json=payload)
    assert response.status_code == 410
    data = response.json()
    assert data["detail"]["code"] == "legacy_route_retired"
    assert data["detail"]["replacement"] == "/api/v1/films"


def test_video_provider_catalog_uses_canonical_consumer(monkeypatch):
    from app.api.v1.endpoints import videos as videos_endpoint

    class FakeConsumerCatalog:
        async def models(self):
            return {"data": [
                {"id": "video/auto"},
                {"id": "video/labs.google/auto"},
                {"id": "session-pool/auto"},
            ]}

        async def aclose(self):
            return None

    monkeypatch.setattr(videos_endpoint, "ChatPoolClient", lambda: FakeConsumerCatalog())
    response = TestClient(app).get("/api/v1/videos/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["transport"] == "http://127.0.0.1:8190/v1"
    assert body["providers"] == [{
        "name": "labs.google", "route": "video/labs.google/auto", "reachable": True,
    }]


def test_direct_audio_speech_endpoint_is_retired():
    client = TestClient(app)
    payload = {
        "input": "In the neon-lit shadows of Neo-Tokyo...",
    }
    response = client.post("/api/v1/audio/speech", json=payload)
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "legacy_route_retired"


def test_mock_film_execution_is_rejected_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    client = TestClient(app)
    create = client.post("/api/v1/films/", json={"script": "A bounded production check."})
    assert create.status_code == 422
    assert create.json()["detail"]["code"] == "mock_backend_disabled_in_production"

    tick = client.post("/api/v1/films/not-created/tick?backend=mock")
    assert tick.status_code == 422
    assert tick.json()["detail"]["code"] == "mock_backend_disabled_in_production"


def test_projects_crud_endpoint():
    client = TestClient(app)
    # Create project
    create_res = client.post("/api/v1/projects/", json={"title": "Cyber Samurai Animation"})
    assert create_res.status_code == 200
    proj = create_res.json()
    proj_id = proj["id"]

    # Get project
    get_res = client.get(f"/api/v1/projects/{proj_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Cyber Samurai Animation"

    assert client.get("/api/v1/projects/does-not-exist").status_code == 404
    assert client.put("/api/v1/projects/does-not-exist", json={"title": "no upsert"}).status_code == 404


def test_pipeline_run_endpoint():
    client = TestClient(app)
    payload = {
        "idea": "A robot finds a glowing blue flower on a dystopian planet",
        "style": "Sci-Fi",
    }
    response = client.post("/api/v1/projects/test-proj-123/pipeline/run", json=payload)
    assert response.status_code == 410
    data = response.json()
    assert data["detail"]["code"] == "legacy_route_retired"


def test_legacy_studio_client_is_quarantined_without_local_opt_in(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("OIOI_ENABLE_LEGACY_STUDIO_PIPELINE", raising=False)
    with pytest.raises(OmniRouteError, match="quarantined"):
        OmniRouteClient()


def test_character_reference_upload_is_app_controlled_and_provider_free():
    client = TestClient(app)
    response = client.post(
        "/api/v1/assets/character-references?character_name=Unit-7&kind=sheet",
        files={"image": ("untrusted-name.png", b"\x89PNG\r\n\x1a\nlocal-reference", "image/png")},
    )
    assert response.status_code == 200
    asset = response.json()
    assert asset["characterName"] == "Unit-7"
    assert len(asset["sha256"]) == 64
    stored = client.get(asset["referenceUrl"])
    assert stored.status_code == 200
    assert stored.headers["content-type"].startswith("image/png")


def test_approved_crew_admission_uses_durable_local_film_graph_without_provider():
    client = TestClient(app)
    response = client.post(
        "/api/v1/films/crew-admissions",
        json={
            "crew_outputs": {role.lower().replace(" ", "_"): value for role, value in MOCK_AGENT_JSON.items()},
            "target_seconds": 10,
            "character_refs": {"Unit-7": {"sheetUrl": "https://assets.example/unit-7-sheet.png"}},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["directorApproved"] is True
    assert data["admission"]["accepted"] is True
    film_id = data["admission"]["film"]["id"]
    summary = client.get(f"/api/v1/films/{film_id}")
    assert summary.status_code == 200
    assert summary.json()["logical_shots"] == 2


@pytest.mark.asyncio
async def test_canonical_crew_run_uses_only_the_consumer_chat_client(monkeypatch):
    """The replacement UI endpoint must not reach the ProviderRegistry."""
    replies = iter(MOCK_AGENT_JSON.values())

    class FakeConsumerChat:
        async def message(self, content, *, max_tokens, model, json_mode=False):
            assert model == "session-pool/auto"
            assert "SYSTEM:" in content
            assert json_mode is True
            return SimpleNamespace(
                text=json.dumps(next(replies)),
                provider="test-gateway",
                session="seat-1",
                tenant="tenant-test",
            )

        async def aclose(self):
            return None

    monkeypatch.setattr(films_endpoint, "ChatPoolClient", lambda *_args, **_kwargs: FakeConsumerChat())
    app.dependency_overrides[get_current_user] = lambda: User(
        id="canonical-crew-user", email="canonical@example.test", is_active=True,
    )
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/films/crew-runs", json={
                "idea": "A robot finds a luminous flower", "target_seconds": 10,
            })
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["transport"] == "http://127.0.0.1:8190/v1"
            assert body["directorApproved"] is True
            assert body["film_id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_models_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/models/")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert len(data["video_models"]) >= 25
    assert len(data["image_models"]) >= 25
    assert len(data["llm_models"]) >= 25


def test_styles_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/styles/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 150


def test_providers_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/providers/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "providers" in data
