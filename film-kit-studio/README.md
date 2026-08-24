# Film Kit Studio

A browser-based AI filmmaking platform — generate short cinematic films from text
prompts and visual style configurations. Migrated from the local `film_kit.py` CLI
into a full-stack web app (Next.js + FastAPI).

![stack](https://img.shields.io/badge/Next.js-14-black) ![stack](https://img.shields.io/badge/FastAPI-0.115-009688) ![stack](https://img.shields.io/badge/NVIDIA-NIM-76b900)

## Tech Stack

| Layer        | Technology                                                        |
| ------------ | ----------------------------------------------------------------- |
| Frontend     | Next.js 14 (App Router), React 18, Tailwind CSS, TypeScript       |
| Backend      | Python, FastAPI, SQLAlchemy 2.0 (async)                           |
| Inference    | NVIDIA NIM — Llama 3.1 70B (script), pluggable visual provider    |
| Narration    | Pluggable TTS — edge-tts (free) or ElevenLabs                     |
| Music        | Pluggable — FFMPEG synthesised bed (free) or Suno                 |
| Video        | FFMPEG (Ken Burns, mux, concat/xfade, ambient bed, SRT)           |
| Database     | SQLite (default, via `aiosqlite`) or PostgreSQL                   |

## Three Major New Features (v2)

### 1. Pluggable Script LLM — NIM default + OpenAI / Anthropic / Gemini
The script/storyboard generation layer is now **provider-agnostic**. `SCRIPT_PROVIDER`
(env) chooses the backend: `nim` (free, default), `openai`, `anthropic`, or `gemini`.
Each provider implements the same `ScriptLLMProvider` protocol so the pipeline code
stays unchanged. Cost & quality trade-offs are per-provider; zero keys required for
the free NIM path.

### 2. Human-in-the-loop Review / Trim / Reorder before Final Stitch
After clips are rendered, a new **Review Panel** lets you:
- **Trim** per-scene in/out points (seconds) — FFMPEG accurate-seek re-encode
- **Per-scene transition override** — cut / crossfade / inherit global
- **Include / exclude** scenes from the final film
- **Drag-and-drop reorder** (native HTML5 DnD, already wired)

All edits persist via the existing `PATCH /api/projects/{id}/scenes/{scene_id}`
endpoint; no new backend routes needed. The `run_stitching` task reads these
fields and builds the final clip list accordingly.

### 3. Character Reference-Image Conditioning for Visual Consistency
- **Character CRUD** (`/api/projects/{id}/characters`) with name, description,
  and **multipart reference image upload** (served via existing media endpoint).
- Each scene can be assigned a character (`character_id` FK on `Scene`).
- During visual generation:
  - If a scene has a character with a reference image → provider receives
    `reference_image=Path` (image-to-video conditioning).
  - The character's `description` is **folded into the cinematic prompt**
    (`character: <desc>`) as an identity-lock fallback that works even with the
    free Cosmos tier and no uploaded image.
- **Veo / Kling / Cosmos** all implement the `reference_image` protocol:
  - Veo: `instances[].image` (base64 / data URI)
  - Kling: switches to `/v1/videos/image2video` endpoint with `image` field
  - Cosmos: switches `mode` to `IMAGE2WORLD` + `image` field

## Pluggable Provider Tiers

Every generation layer is **pluggable**. The free default works with zero API
keys; set the relevant key + provider flag to opt into a cinematic tier.

| Layer   | Free default            | Cinematic upgrade         | Env flag           | Key needed            |
| ------- | ----------------------- | ------------------------- | ------------------ | --------------------- |
| Script  | NVIDIA NIM (Llama 3.1)  | OpenAI / Anthropic / Gemini| `SCRIPT_PROVIDER` | `OPENAI_API_KEY` etc. |
| Visuals | NVIDIA Cosmos3 (NIM)    | Google Veo 3.1 / Kling 3.0| `VISUAL_PROVIDER`  | `GEMINI_API_KEY` / `KLING_*` |
| Voice   | edge-tts                | ElevenLabs (v3)           | `VOICE_PROVIDER`   | `ELEVENLABS_API_KEY`  |
| Music   | FFMPEG synth bed        | Suno (via gateway)        | `MUSIC_PROVIDER`   | `SUNO_API_KEY`        |

If a provider flag names a tier whose key is unset, the app **silently falls
back** to the free default and logs a warning — so the pipeline never breaks.

### Cost reference (approximate, 2026)

| Provider   | Rough cost                       |
| ---------- | -------------------------------- |
| Cosmos     | free (NIM credits)               |
| Veo 3.1    | ~$0.10–0.40 / second of video    |
| Kling 3.0  | ~$0.075–0.14 / second            |
| NIM LLM    | free (NIM credits)               |
| OpenAI GPT-4o | ~$5 / 1M tokens (input)        |
| Anthropic Claude 3.5 | ~$3 / 1M tokens (input)   |
| edge-tts   | free                             |
| ElevenLabs | ~$0.10 / 1,000 chars (10k free/mo) |
| FFMPEG bed | free                             |
| Suno       | gateway-dependent (~$0.05–0.20/track) |

## Cinematography Direction

The script-generation LLM emits a **structured cinematography schema** per
scene — `shot_type`, `lens`, `lighting`, `camera_move`, `color_grade` — in
addition to narration and visual prompt. At generation time these are composed
with the global `CINEMATOGRAPHY_STYLE` prefix into one fluent, filmic prompt
handed to the visual provider. This is the single biggest free quality lever
and requires no API changes. The storyboard UI surfaces these as color-coded
badges on each scene card.

## Architecture

```
backend/
  main.py                 FastAPI app, CORS, lifespan (DB init)
  config.py               Settings + constants (aspects, voices, styles, system prompt)
  database.py             Async SQLAlchemy engine/session
  models.py               Project / Scene / Character / Task ORM
  schemas.py              Pydantic request/response models
  routers/
    projects.py           CRUD + scene edit + reorder
    pipeline.py           Trigger + monitor (poll + SSE) generation tasks
    characters.py         Character CRUD + multipart image upload
    media.py              Serve generated images/clips/videos/srt
  services/
    nim_llm.py            NVIDIA NIM LLM (script/storyboard + cinematography schema)
    script_providers/     Pluggable script LLMs: nim / openai / anthropic / gemini
    pipeline.py           Orchestrates the 5-step pipeline (+ trim/review hooks)
    visual_providers/     Pluggable visuals: cosmos (free) / veo / kling (with reference_image)
    voice_providers/      Pluggable TTS: edge (free) / elevenlabs
    music_providers/      Pluggable score: ffmpeg bed (free) / suno
  tasks/
    task_manager.py       Non-blocking tasks + SSE event queue
  utils/
    ffmpeg_ops.py         All FFMPEG/ffprobe subprocess commands (trim_clip added)
    token_bucket.py       RPM guard + TPM meter (migrated from film_kit.py)
    json_extract.py       Robust JSON-array extraction from LLM output

frontend/
  app/
    page.tsx              Dashboard: story idea, aspect ratio, visual style
    projects/[id]/page.tsx   Project workspace (storyboard + pipeline + player)
  components/
    StoryboardView.tsx    Draggable + editable scene grid + character dropdown
    ReviewPanel.tsx       Trim in/out, transition, include/exclude, drag-reorder
    CharacterPanel.tsx    Character CRUD + drag-drop reference image upload
    PipelinePanel.tsx     Step-by-step / full-pipeline controls
    VideoPlayer.tsx       Final film player with subtitles
  lib/
    api.ts                Typed API client (character CRUD, upload, widened updateScene)
    useSSE.ts             Server-Sent Events hook
    types.ts              Shared TS interfaces (Character, Scene trim/transition fields)
```

## Pipeline

1. **Script & Storyboard** — Llama 3.1 70B (via NIM) or pluggable provider returns a JSON array of
   `{narration, visual_prompt, shot_type, lens, lighting, camera_move, color_grade}` scenes.
2. **Visual Generation** — Cosmos3 Generator NIM (`TEXT2WORLD`) or Veo/Kling (with optional `reference_image` for image-to-video conditioning), dynamic resolution per aspect ratio.
3. **Audio & Narration** — `edge-tts` per scene + FFMPEG ambient music bed (sine drones + pink noise).
4. **Clip Rendering** — FFMPEG: Ken Burns `zoompan` fallback (if a Cosmos video isn't available), audio muxed with `-async 1`.
5. **Stitching** — `concat` demuxer (hard cuts) **or** `xfade` crossfade chain, respecting per-scene `trim_start_seconds`/`trim_end_seconds`, `transition_type`, and `included` flag, plus synchronized `.srt` subtitles.

All steps run as non-blocking background tasks with **SSE** progress streaming
(and a polling fallback). NIM calls use a token-bucket RPM guard with retry +
backoff, migrated from the original script.

## Prerequisites

- **Node.js 18+** and npm
- **Python 3.10+**
- **FFmpeg** + **ffprobe** on your `PATH`
- A free **NVIDIA NIM API key** — get one at <https://build.nvidia.com> → API Keys

## Setup & Run

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # then edit .env and set NIM_API_KEY
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be at <http://localhost:8000> (interactive docs at `/docs`).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The frontend proxies `/api/*` to the backend
(see `next.config.js` rewrites), so no CORS or separate base URL is needed in dev.

## Environment Variables

| Variable             | Default                              | Description                          |
| -------------------- | ------------------------------------ | ------------------------------------ |
| `NIM_API_KEY`        | _(empty — required for free tier)_   | NVIDIA NIM API key                   |
| `NIM_LLM_MODEL`      | `meta/llama-3.1-70b-instruct`        | Script generation model              |
| `NIM_COSMOS_MODEL`   | `nvidia/cosmos-3-generator`          | Visual generation model (Cosmos)     |
| `NIM_RPM`            | `40`                                 | NIM rate limit (requests/minute)     |
| `SCRIPT_PROVIDER`    | `nim`                                | `nim` \| `openai` \| `anthropic` \| `gemini` |
| `VISUAL_PROVIDER`    | `cosmos`                             | `cosmos` \| `veo` \| `kling`         |
| `VOICE_PROVIDER`     | `edge`                               | `edge` \| `elevenlabs`               |
| `MUSIC_PROVIDER`     | `ffmpeg`                             | `ffmpeg` \| `suno`                   |
| `OPENAI_API_KEY`     | _(empty)_                            | Required for `SCRIPT_PROVIDER=openai`|
| `OPENAI_MODEL`       | `gpt-4o`                             | OpenAI model                         |
| `ANTHROPIC_API_KEY`  | _(empty)_                            | Required for `SCRIPT_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL`    | `claude-3-5-sonnet-20241022`         | Anthropic model                      |
| `GEMINI_API_KEY`     | _(empty)_                            | Required for `VISUAL_PROVIDER=veo` / `SCRIPT_PROVIDER=gemini` |
| `GEMINI_MODEL`       | `gemini-1.5-pro`                     | Gemini model                         |
| `KLING_API_KEY`/`_SECRET` | _(empty)_                        | Required for `VISUAL_PROVIDER=kling` |
| `ELEVENLABS_API_KEY` | _(empty)_                            | Required for `VOICE_PROVIDER=elevenlabs` |
| `SUNO_API_KEY`/`_BASE_URL` | _(empty)_                      | Required for `MUSIC_PROVIDER=suno`   |
| `CINEMATOGRAPHY_STYLE`| _(see config)_                      | Global style prefix for visual prompts |
| `DEFAULT_TRANSITION_MODE`| `cut`                            | Global transition: `cut` \| `crossfade` |
| `DEFAULT_TRANSITION_DURATION`| `0.5`                         | Crossfade duration (seconds)         |
| `DEFAULT_TRIM_START` | _(empty)_                            | Default trim start (seconds)         |
| `DEFAULT_TRIM_END`   | _(empty)_                            | Default trim end (seconds)           |
| `DATABASE_URL`       | `sqlite+aiosqlite:///./...db`        | DB URL (swap for Postgres in prod)   |
| `FRONTEND_URL`       | `http://localhost:3000`              | Allowed CORS origin                  |
| `PROJECTS_DIR`       | `./projects`                         | Generated media storage              |

## Database Migrations (zero-downtime for dev DBs)

The app uses `Base.metadata.create_all` — new **tables** (`characters`) create
automatically. New **columns** on the existing `scenes` table
(`trim_start_seconds`, `trim_end_seconds`, `transition_type`,
`transition_duration`, `included`, `character_id`) are added at startup via an
idempotent `ALTER TABLE ... ADD COLUMN` inside a try/except (SQLite raises on
duplicate column → ignored). Existing SQLite dev databases upgrade in place
without a wipe.

## Notes

- The legacy Pollinations.ai text-to-image fallback has been **removed** in favor
  of the NVIDIA Cosmos3 Generator NIM. Ken Burns image animation still works if
  static images are present.
- FFMPEG commands are isolated in `backend/utils/ffmpeg_ops.py` per the
  modular-architecture constraint.
- All three cinematic-tier visual providers (Veo, Kling, Cosmos) implement the
  `reference_image` protocol for character-consistent image-to-video.