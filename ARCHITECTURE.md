# ARCHITECTURE — OiiOii.ai 100% Clone

> Companion to `PLAN.md`. Defines components, interfaces, and data flow for the
> free-tier, NVIDIA-free AI Animation Agent Team. NVIDIA NIM is a TOTAL NO-GO
> (AC-10); every inference path routes through `ProviderRegistry`.

## 1. Components

### 1.1 Provider Layer (`backend/providers/`)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        ProviderRegistry (singleton)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │ OpenRouter   │ │ Groq         │ │ Gemini (NEW) │ │ Cloudflare   │ │
│  │ chat/img/vid │ │ chat/embed   │ │ chat/img/vid │ │ chat/img/emb│ │
│  ├──────────────┤ ├──────────────┤ ├──────────────┤ ├─────────────┤ │
│  │ Cerebras     │ │ Cohere       │ │ Pollinations │ │              │ │
│  │ chat         │ │ chat/embed   │ │ image (keyless)│             │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │
│  Health · Cooldown · Priority · Failover · NVIDIA hard-block (AC-10)  │
└──────────────────────────────────────────────────────────────────────┘
```

- **`base.py`** — `AIProviderAdapter` ABC + Pydantic contracts
  (`ChatCompletionRequest/Response/Chunk`, `ImageGenerationRequest/Response`,
  `VideoGenerationRequest/Response`, `EmbeddingRequest/Response`, `Model`,
  `ProviderHealth`/`ProviderStatus`).
- **`registry.py`** — `ProviderRegistry`: lazy factories, priority ordering,
  per-provider health + exponential cooldown, `get_adapter(capability, prefer)`
  with failover, `report_success/failure`, `snapshot()`. Module singleton via
  `get_registry()`/`reset_registry()`.
- **Adapters** — each implements `AIProviderAdapter`:
  - `openrouter_adapter.py` (chat/image/video/embedding, retry/backoff)
  - `groq_adapter.py` (chat/embedding)
  - `cerebras.py` (chat; embeddings delegated)
  - `cloudflare.py` (chat/image/embedding; video delegated)
  - `cohere.py` (chat/embedding; real SSE streaming)
  - `gemini.py` **(NEW)** — multimodal chat/image/video/audio via Google AI Studio
  - `pollinations.py` **(NEW)** — keyless text-to-image fallback
- **`app/services/provider_service.py`** — `init_registry()` reads `settings`,
  registers only providers with configured keys (Pollinations always registered
  as keyless image fallback), ordered by `PROVIDER_PRIORITY`.

### 1.2 Agent Pipeline (`backend/agent_pipeline.py` + `agent_contracts.py`)

```
idea ─▶ Scriptwriter ─▶ Art Director ─┬─▶ Character Designer ─┐
                                       ├─▶ Scene Designer ─────┤
                                       │                       ▼
                                       │                     Animator ─▶ Sound Director ─▶ Director ─▶ short film
                                       └──────────────────────────────────────────────────────────────┘
```

- **`agent_contracts.py`** — typed Pydantic I/O for each of the 7 agents
  (`ScriptwriterInput/Output` … `DirectorInput/Output`) + `AgentOrchestrator` ABC.
- **`agent_pipeline.py`** — `AgentOrchestrator` implementation; each stage:
  1. builds the agent's typed input,
  2. selects a registry adapter by capability (`chat`/`image`/`video`/`audio`),
  3. persists an `AgentExecution` row (pending→running→completed/failed),
  4. returns typed output consumed by the next stage.
- **Resumable**: a failed `AgentExecution` can be retried by id without re-running
  earlier completed stages.

### 1.3 API Layer (`backend/app/api/v1/`)

| Endpoint | Method | Capability | Notes |
|---|---|---|---|
| `/chat/completions` | POST | chat | OpenAI-compatible |
| `/chat/stream` | GET | chat | SSE token stream |
| `/images/generations` | POST | image | Pollinations/Cloudflare/Gemini |
| `/videos/generations` | POST | video | Gemini Veo / Ken-Burns fallback |
| `/audio/speech` | POST | audio | Gemini/edge-tts |
| `/projects` | POST/GET | — | CRUD |
| `/projects/{id}/pipeline/run` | POST | — | runs `AgentOrchestrator.run_pipeline` |
| `/models` | GET | — | from `models_registry` |
| `/styles` | GET | — | from `styles_registry` |
| `/providers/health` | GET | — | `registry.snapshot()` |

### 1.4 Registries (`backend/`)
- **`models_registry.py`** — 25+ models per category (Video/Image/LLM), each
  mapped to a real free-tier provider id (no `example.com`).
- **`styles_registry.py`** — 150+ named styles with prompt suffixes.

### 1.5 Frontend (`oioi/` — Next.js + Prisma)
- **Canvas** — model picker (grouped Video/Image/LLM), style picker (150+),
  concurrent generation queue, linked editing, first/last-frame reference.
- **Streaming chat** — SSE consumer for `/chat/stream`.
- **Generation panels** — image/video/audio forms hitting v1 endpoints.
- **State** — Prisma `Project`/`Asset` mirrored to backend ORM.

## 2. Data Flow

### 2.1 Chat completion (streaming)
```
Client ──GET /chat/stream──▶ FastAPI ──▶ ProviderRegistry.get_adapter("chat")
  ──▶ {Groq|OpenRouter|Cerebras|Cohere|Gemini}.chat_completion_stream()
  ──▶ SSE chunks ──▶ Client (token-by-token render)
```

### 2.2 Image generation (keyless-first)
```
Client ──POST /images/generations──▶ FastAPI
  ──▶ ProviderRegistry.get_adapter("image", prefer="pollinations")
  ──▶ PollinationsAdapter.generate_image() ──▶ image URL ──▶ Client
  (fallback: Cloudflare @cf/stable-diffusion-xl → Gemini 2.5 Flash image)
```

### 2.3 Idea → short film pipeline
```
Client ──POST /projects/{id}/pipeline/run {idea, style, duration}
  ──▶ AgentOrchestrator.run_pipeline()
      ├─ Scriptwriter  (chat)  ──▶ AgentExecution(pending→completed) + Asset(script)
      ├─ Art Director  (chat)  ──▶ AgentExecution + style guide
      ├─ Character Designer (image) ──▶ AgentExecution + Asset(character sheets)
      ├─ Scene Designer (image) ──▶ AgentExecution + Asset(scene backgrounds)
      ├─ Animator (video) ──▶ AgentExecution + Asset(clips)
      ├─ Sound Director (audio) ──▶ AgentExecution + Asset(narration/music)
      └─ Director (chat) ──▶ AgentExecution + final notes
  ──▶ stitched short film Asset ──▶ Client
```

### 2.4 Provider failover
```
get_adapter(cap) → candidates sorted by priority, skip cooldown
  → try adapter.chat_completion() → success: report_success(name, latency)
  → on HTTPError/429/5xx: report_failure(name) → next candidate
  → all fail: RuntimeError("No provider available")
```

## 3. Tech Stack
- **Backend**: FastAPI + Pydantic v2 + SQLAlchemy 2 (ORM) + Alembic + httpx + pytest.
- **Providers**: OpenRouter, Groq, Cerebras, Cloudflare Workers AI, Cohere,
  Google Gemini (AI Studio), Pollinations (keyless).
- **Frontend**: Next.js 14 (App Router) + Prisma + Tailwind + Jest.
- **Storage**: local filesystem (`./storage`) pluggable to S3/GCS.
- **Queue**: optional Celery + Redis for background pipeline runs.

## 4. Interface Stubs (contracts only — implemented in IMPLEMENTATION phase)

### 4.1 `backend/providers/gemini.py`
```python
class GeminiAdapter(AIProviderAdapter):
    def __init__(self, api_key: str, base_url: str = "https://generativelanguage.googleapis.com/v1beta"): ...
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse: ...
    async def chat_completion_stream(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]: ...
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse: ...
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse: ...
    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse: ...
    async def list_models(self) -> List[Model]: ...
    async def health_check(self) -> ProviderHealth: ...
    def get_provider_name(self) -> str: return "gemini"
```

### 4.2 `backend/providers/pollinations.py`
```python
class PollinationsAdapter(AIProviderAdapter):
    def __init__(self, base_url: str = "https://image.pollinations.ai/prompt"): ...
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse: ...
    # chat/video/embedding raise NotImplementedError (image-only keyless fallback)
    def get_provider_name(self) -> str: return "pollinations"
```

### 4.3 `backend/agent_pipeline.py` (orchestrator)
```python
class AnimationAgentOrchestrator(AgentOrchestrator):
    def __init__(self, registry: ProviderRegistry, db_session): ...
    async def run_scriptwriter(self, input: ScriptwriterInput) -> ScriptwriterOutput: ...
    async def run_art_director(self, input: ArtDirectorInput) -> ArtDirectorOutput: ...
    async def run_character_designer(self, input: CharacterDesignerInput) -> CharacterDesignerOutput: ...
    async def run_scene_designer(self, input: SceneDesignerInput) -> SceneDesignerOutput: ...
    async def run_animator(self, input: AnimatorInput) -> AnimatorOutput: ...
    async def run_sound_director(self, input: SoundDirectorInput) -> SoundDirectorOutput: ...
    async def run_director(self, input: DirectorInput) -> DirectorOutput: ...
    async def run_pipeline(self, prompt: str, duration: Optional[int] = None, style: Optional[str] = None) -> Dict[str, Any]: ...
    async def retry_agent(self, execution_id: str) -> AgentOutput: ...
```

### 4.4 `backend/app/api/v1/endpoints/` (routers)
```python
# chat.py
router = APIRouter()
@router.post("/completions")
async def chat_completions(req: ChatCompletionRequest): ...
@router.get("/stream")
async def chat_stream(req: ChatCompletionRequest): ...  # StreamingResponse SSE

# images.py / videos.py / audio.py / projects.py / pipeline.py / models.py / styles.py / providers.py
router = APIRouter()
# POST/GET handlers delegating to ProviderRegistry / registries / AgentOrchestrator
```

### 4.5 `backend/app/api/v1/api.py` (aggregator — replaces NVIDIA-only router)
```python
api_router = APIRouter()
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(images.router, prefix="/images", tags=["Images"])
api_router.include_router(videos.router, prefix="/videos", tags=["Videos"])
api_router.include_router(audio.router, prefix="/audio", tags=["Audio"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(pipeline.router, prefix="/projects", tags=["Pipeline"])
api_router.include_router(models.router, prefix="/models", tags=["Models"])
api_router.include_router(styles.router, prefix="/styles", tags=["Styles"])
api_router.include_router(providers.router, prefix="/providers", tags=["Providers"])
# NOTE: nim router is REMOVED (AC-10).
```

## 5. AC-10 Enforcement
- `backend/nim_client.py` remains a hard `ImportError` stub.
- `ProviderRegistry.register/register_factory` raise `ValueError` on any name
  containing `nim`/`nvidia`.
- A guard test (`tests/test_ac10_no_nvidia.py`) asserts:
  - importing `backend.nim_client` raises `ImportError`,
  - `ProviderRegistry().register("nvidia", ...)` raises `ValueError`,
  - no endpoint router references NVIDIA.
