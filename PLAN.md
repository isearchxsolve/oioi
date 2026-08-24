# PLAN — OiiOii.ai 100% Clone (NVIDIA NIM removed; free-tier providers only)

## Goal
Finish every pending task required to make this codebase a 100% functional clone of **oiioii.ai** — the AI Animation Agent Team that turns ideas into characters, scenes, storyboards, and short films. NVIDIA NIM is a **TOTAL NO-GO** (AC-10); all inference must route through free-tier, no-credit-card provider adapters.

## Product Reference (researched)
Source product: **oiioii.ai** (NOT oioi.com — confirmed via web search; the existing codebase already brands itself "OiiOii.ai Clone").
- **AI Animation Canvas** — 25+ AI models (Sora2, Kling 3.0, Seedance 2.0, GPT-image-2, ...), 150+ built-in styles, concurrent generation, linked editing, video frame reference on one canvas.
- **AI Video Generation** — 17+ video models, first-frame + last-frame reference, universal style guidance, concurrent batch rendering.
- **7 specialized AI agents** (already modeled in `backend/app/models/agent_execution.py`): Scriptwriter, Art Director, Character Designer, Scene Designer, Animator, Sound Director, Director.
- **Idea → short film pipeline**: idea → script → storyboard images → narration → clips → stitched film.

## Current Codebase State (audited)
- `backend/providers/` — multi-provider adapter layer EXISTS: `base.py` (abstract `AIProviderAdapter` + Pydantic contracts), `registry.py` (priority/health/failover `ProviderRegistry`, hard-blocks NVIDIA), `openrouter_adapter.py`, `groq_adapter.py`, `cerebras.py`, `cloudflare.py`, `cohere.py`. `backend/app/services/provider_service.py` wires configured providers into the registry from `settings`.
- `backend/nim_client.py` — DEPRECATED stub that raises `ImportError` (AC-10 enforced).
- `backend/app/` — FastAPI skeleton: `api/v1/endpoints`, `core/{config,database}`, ORM `models/{agent_execution,asset,model,project,style,user}`, `schemas`, `services`.
- `backend/` root modules: `canvas.py`, `generation.py`, `styles_registry.py`, `agent_pipeline.py`, `agent_contracts.py`, `models_registry.py` (25+ models per category, but mostly placeholder `example.com` URLs).
- `oioi/` — Next.js + Prisma frontend, but `src/app/page.tsx` is a **one-line stub** ("OiiOii Clone"). No canvas UI, no agent UI, no video/image generation UI.
- `backend/tests/` — only `test_nim_client*.py` (deprecated NVIDIA tests). **No tests for the provider layer, registry, agents, canvas, or generation.**
- **Gaps**: image/video generation providers (fal/Replicate) referenced but not implemented; Cerebras embeddings `NotImplementedError`; Cohere streaming not implemented; Cloudflare video `NotImplementedError`; agent pipeline incomplete; frontend essentially empty.

## Requirements

### R1 — Provider layer (free-tier, NVIDIA-free)
1. Every inference call routes through `ProviderRegistry.get_adapter(capability=...)` with automatic failover; no code path may import or call NVIDIA NIM (enforced by AC-10 test).
2. Adapters must be complete and tested for: **OpenRouter** (chat/image/video/embedding), **Groq** (chat/embedding), **Cerebras** (chat), **Cloudflare Workers AI** (chat/image/embedding), **Cohere** (chat/embedding), **Google Gemini** (chat/image/video/audio — multimodal, NEW adapter to add).
3. Add a **GeminiAdapter** (`providers/gemini.py`) for free multimodal image/video generation (Gemini 2.5 Flash image gen, Veo video) to replace NVIDIA's image/video role.
4. Add **PollinationsAdapter** (`providers/pollinations.py`) — keyless free text-to-image fallback so image generation works with zero configured keys.
5. Fix stubs: Cerebras embeddings (delegate to Cohere/OpenRouter), Cohere streaming (real SSE), Cloudflare video (delegate to Gemini/fal).
6. `provider_service.init_registry()` registers only providers with configured keys; Pollinations always registered as keyless image fallback.
7. Health checks, retry/backoff, and quota cooldown already in `registry.py` — wire them into every endpoint.

### R2 — 7-agent animation pipeline
1. Implement `agent_pipeline.py` end-to-end: idea → Scriptwriter → Art Director → Character Designer → Scene Designer → Animator → Sound Director → Director → short film.
2. Each agent uses `agent_contracts.py` typed I/O; each run persists an `AgentExecution` row (status pending→running→completed/failed).
3. Agents call the registry with the right capability (chat for text agents, image for visual agents, video for animator, audio for sound director via Gemini/edge-tts).
4. Pipeline is resumable: a failed agent can be retried without re-running earlier stages.

### R3 — AI Animation Canvas (frontend)
1. Next.js canvas UI matching oiioii.ai: model picker (25+ models grouped Video/Image/LLM), 150+ style picker, concurrent generation queue, linked editing, first/last-frame reference.
2. Canvas state persisted via Prisma; assets linked to `Project` + `Asset` ORM.
3. Real-time streaming chat (SSE) from backend `/api/v1/chat/stream`.
4. Image/video generation panels calling `/api/v1/images/generations` and `/api/v1/videos/generations`.

### R4 — Models & styles registries
1. `models_registry.py` — replace placeholder `example.com` URLs with real free-tier model IDs mapped to providers (e.g. `groq/llama-3.3-70b`, `gemini-2.5-flash`, `@cf/stable-diffusion-xl`, `pollinations/flux`).
2. `styles_registry.py` — 150+ named styles with prompt suffixes.
3. Registries are the single source of truth for both backend routing and frontend pickers.

### R5 — API surface (FastAPI v1)
1. `POST /api/v1/chat/completions` + `GET /api/v1/chat/stream` (SSE).
2. `POST /api/v1/images/generations`, `POST /api/v1/videos/generations`, `POST /api/v1/audio/speech`.
3. `POST /api/v1/projects`, `GET /api/v1/projects/{id}`, `POST /api/v1/projects/{id}/pipeline/run`.
4. `GET /api/v1/models`, `GET /api/v1/styles`, `GET /api/v1/providers/health`.
5. All endpoints use the registry; none reference NVIDIA.

### R6 — Tests (TDD)
1. AC-10 guard test: importing/calling any NVIDIA path fails.
2. Registry failover + health/cooldown tests.
3. Each adapter mocked-HTTP test (chat, stream, image/video where supported, list_models, health_check).
4. Agent pipeline stage-by-stage test with mocked registry.
5. API endpoint integration tests via FastAPI TestClient.
6. Frontend component + canvas-state tests (Jest, already configured in `oioi/`).

## Risks
- **R-RISK-1 — Free-tier rate limits**: Groq 30 RPM, Gemini 10 RPM/250 RPD, Cloudflare 10k neurons/day. Mitigation: registry failover + cooldown + Pollinations keyless image fallback + request queuing.
- **R-RISK-2 — No free video generation**: true free text-to-video is scarce. Mitigation: Gemini Veo free tier where available; otherwise fall back to image→Ken-Burns clip stitching (pattern proven in `film_kit.py`).
- **R-RISK-3 — Provider API drift**: free tiers change endpoints/models. Mitigation: `health_check` + `list_models` live discovery; registries refreshable at runtime.
- **R-RISK-4 — Frontend scope**: oiioii.ai canvas is large. Mitigation: ship core (model/style pickers + generation panels + streaming chat) first; advanced linked-editing as follow-up.
- **R-RISK-5 — NVIDIA regression**: stale imports could re-introduce NVIDIA. Mitigation: AC-10 guard test in CI; `nim_client.py` stays a hard-fail stub.
- **R-RISK-6 — Key configuration friction**: users without keys get dead ends. Mitigation: Pollinations keyless image + Cloudflare/Groq email-only signup; clear `.env.example`.
- **R-RISK-7 — Cohere/Cerebras stubs**: incomplete adapters break failover. Mitigation: complete or explicitly mark unsupported capabilities so registry skips them.

## Acceptance Criteria
- **AC-1**: `pytest backend/tests/` is green and covers registry, every adapter, agent pipeline, and all v1 API endpoints.
- **AC-2**: `npm test` (oioi frontend) is green and covers canvas state, model/style pickers, streaming chat, generation panels.
- **AC-3**: A full `idea → short film` pipeline run succeeds end-to-end using only free-tier providers (no NVIDIA).
- **AC-4**: Frontend canvas renders 25+ models (grouped Video/Image/LLM) and 150+ styles from the backend registries.
- **AC-5**: Streaming chat works via SSE with token-by-token rendering.
- **AC-6**: Image generation returns a real image URL from Pollinations (keyless) or Cloudflare/Gemini.
- **AC-7**: Video generation returns a real video URL from Gemini Veo, or a stitched Ken-Burns clip fallback.
- **AC-8**: Provider health dashboard (`GET /api/v1/providers/health`) reports live status with failover demonstrated.
- **AC-9**: `.env.example` documents every free-tier key; app runs with zero keys (Pollinations + public Groq/Cloudflare trial) for a demo.
- **AC-10**: **NVIDIA NIM is a TOTAL NO-GO** — a guard test asserts no module imports `nim_client` or references NVIDIA; `backend/nim_client.py` remains a hard `ImportError` stub.
- **AC-11**: No `NotImplementedError` remains on a capability a provider advertises in `_FACTORIES` (stubs fixed or capability dropped).
- **AC-12**: `models_registry.py` contains zero `example.com` placeholder URLs; all model IDs map to real free-tier providers.

## Out of Scope (this phase)
- Paid provider billing integration.
- User auth beyond the existing `auth_mock.py`.
- Mobile native apps (oiioiai.com iOS app) — web clone only.
- Animation canvas collaborative multi-user editing.
