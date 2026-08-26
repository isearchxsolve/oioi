# Film Pipeline — Phase 0 Study and Design

_Written before implementation on 2026-08-26. Scope: the OiiOii consumption layer only._

## Existing application study

### Media ingestion and the stitching attachment point

The FastAPI application is bootstrapped in `backend/app/main.py`.  It serves generated
media below `STORAGE_PATH/media` and mounts the API under `/api/v1`.  Today, the interactive
pipeline is exposed by `backend/app/api/v1/endpoints/pipeline.py`.  Its animator delegates
one scene at a time to `agent_pipeline.AnimationPipeline.run_animator`; it reports individual
clip URLs but has no durable clip-job graph.

The reusable media attachment point is `backend/studio_pipeline/media.py`.  It already has
safe subprocess wrappers, media probing, downloading, concat-manifest generation, concat,
audio-mix, and final container helpers.  `backend/studio_pipeline/store.py` gives each run a
durable directory with clip and final-output paths.  The film layer will write completed clips
to a film-specific storage root and call the same ffmpeg executable via a small incremental
assembler.  It intentionally does not alter the legacy one-shot animator endpoint, whose
video-provider adapter speaks a prior router shape.

### Existing jobs, queues, and persistence

There is no production clip-job queue: `backend/app/api/v1/endpoints/jobs.py` is empty and
`active_pipelines` in the legacy pipeline endpoint is process-local.  SQLAlchemy can use
SQLite through `backend/app/core/database.py`, while project and asset metadata live in the
`projects` and `assets` ORM models.  Separately, `RunStore` persists JSON state, an append-only
journal, shot/clip files, and recovery metadata; `EventBus` can replay that journal after a
restart.

The new pipeline therefore supplies a dedicated SQLite store for the business-critical job
graph.  This preserves a transactional uniqueness constraint on `job_key`, which is the
reliable cross-process idempotency mechanism required to avoid duplicate credit spend.  It
does not reuse the process-local map or introduce Redis/Celery merely as a second queue.
`RunStore`/the media helpers remain compatible filesystem artifact utilities rather than a
replacement source of truth for clip states.

### Configuration and inference backend selection

`backend/app/core/config.py` owns configuration via `pydantic-settings`; environment values
override defaults.  Existing chat/video provider selection is through `PROVIDER_PRIORITY`,
`DEFAULT_CHAT_MODEL`, and `DEFAULT_VIDEO_MODEL`.  The legacy direct video adapter points to
the local router at port 8189 but uses its older `/v1/videos/*` route family.

The film layer will use its own explicit `FILM_PIPELINE_*` settings, so the frozen contracts
remain unambiguous: chat defaults to `http://127.0.0.1:20130` and video defaults to **mock**.
Live video is opt-in at CLI/API construction and requires a positive `max_clips`; the live
contract is `/v1/video/*`, not the legacy route family.  The film shot decomposer uses
`pool/auto`, so the supply layer can distribute chat requests across providers.

### Existing asset model

`Project` is a high-level production grouping.  `Asset` represents an image, video, audio,
script, character, or scene and carries its project association, URL, prompt/model metadata,
dimensions, duration, and generic JSON metadata.  Legacy scene data is a JSON dictionary
passed between agents; a completed legacy clip is represented by a `video_url` in that
dictionary.  There is no first-class `Film`, `Shot`, or durable generation-job model.

The new film store consequently models a film request, ordered shots, canonical render jobs,
and append-only assembly segments.  A shot can point to the same canonical render job as one
or more duplicates.  This makes reuse an explicit data relationship instead of copying a
video URL into many unrelated scene records.  It can later be published to `Asset` records
without making SQLAlchemy migrations a prerequisite for reliable job recovery.

## Design before implementation

### Data model and idempotency

A file-scoped SQLite database has four core tables: `films`, `shots`, `clip_jobs`, and
`assembly_segments`.  `clip_jobs.job_key` is `UNIQUE`; inserting a job uses
`INSERT ... ON CONFLICT(job_key) DO NOTHING`, followed by a read of the canonical row.  Thus
the caller-computed stable key (`hash(prompt, duration, image refs, seed, canonical shot
index)`) returns the same job before and after an application restart.  Completed local files
are verified before a job is ever moved back to pending.  A request can fan out only the first
`max_clips` jobs; it never has an unbounded submit loop.

Each film stores its input fingerprint and a cached ordered shot list.  The same script and
generation parameters map to the same film fingerprint, therefore a resume does not call chat
again and does not change prompts.  Every shot contains a persistent style/character bible
and character image references.  Canonicalization removes run-specific wording, and exact
or normalized equivalent prompts share a `canonical_shot_index` and one job.  The API reports
both logical shots and unique generations.

### Contract clients and mock

Typed `ChatPoolClient` and `VideoRouterClient` use only the frozen paths in the brief.  The
video client classifies `503/no_capacity`, `failed/error` prefixed by `wall:`/`auth:`, and
ordinary/transient faults independently.  No client reads files from or imports code from the
supply repository.  A FastAPI mock offers the exact `/v1/video/jobs`, `/v1/video/jobs/{id}`,
`/v1/video/capacity`, and delete routes.  Tests configure latency, deterministic failure
injection, and temporary capacity through its constructor; no request can reach a real router.

### Scheduler and accounting

The orchestrator is a cooperative worker tick rather than a hidden, unbounded background
loop.  On each tick it first polls due remote jobs (at least five seconds apart), then claims
pending jobs subject to both provider and seat caps.  Claims are persisted transactionally.
Transient failures use exponential backoff and move to `quarantined` after a finite retry
budget.  `no_capacity` becomes `parked_capacity` until capacity is reevaluated.  `wall:` and
`auth:` mark the supplied seat unavailable and park work for another seat; they are never
retried on that seat.  The store aggregates reserved/spent credits by film, provider, and
seat, allowing a cost-so-far and projected-total snapshot at every endpoint call.

Admission calls `/v1/video/capacity` before it creates work.  It either refuses with the
numerical shortfall or stores a capacity-wave plan; it never starts a film that is simply
waiting forever.  The planner assumes five-second clips but permits longer configured shot
durations where the provider allows them, which reduces clip count rather than rendering
filler.  It reports both the baseline 2,160 unique clips / 64,800 credits / 540 four-clip
accounts and the reduction achieved by deduplication and footage re-timing.

### Incremental assembly

When a contiguous prefix of logical shots has resolved clips, the assembler writes/reuses a
short concat segment and only joins newly completed contiguous work onto the assembly state.
It does not start an all-clips concat on each update.  The finalization stage applies an audio
bed and final MP4 container once the ordered film is complete.  Where ffmpeg is unavailable,
the assembly remains explicitly pending/failed rather than pretending a film exists.

### Safe operational interface

The CLI defaults to `--backend mock`.  `--backend live` is rejected without both `--live` and
a positive `--max-clips N`; before it sends a job it prints provider, admitted clip count, and
projected credits.  The first permissible live invocation remains `--live --max-clips 3`.
Tests exercise only the mock and use temporary paths.

