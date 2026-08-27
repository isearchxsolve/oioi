# Film Pipeline Delivery Report

**Date:** 2026-08-26
**Scope:** durable long-form Film Pipeline, zero-credit completion, failure resilience, crew-stage correction, and the requested 30-minute output.

## Executive result

A complete 30-minute MP4 with real video and audio has been rendered and verified.

| Property | Verified result |
|---|---|
| Final output | `backend/run_artifacts/signal_tide_30m/artifacts/film_634081fc940b4874b42ff1da2f0324e9/final/film.mp4` |
| Duration | `1800.139323` seconds — 30:00.139 |
| Video | H.264, 1280 × 720, 24 fps |
| Audio | AAC stream muxed into the final MP4 |
| Size | 91,984,983 bytes (~87.7 MiB) |
| SHA-256 | `D5CDFD5BA144E558C6B1D654B6FB97368E3F8881D0354C90E6092059B8A1C447` |
| Logical timeline | 360 ordered five-second shots |
| Segments | Six persisted 60-shot assembly segments |
| Router capacity | Zero seats available |
| Router spend | Zero credits spent |

The output was not a placeholder or merely a completed database row. FFprobe confirmed a separate H.264 video stream and AAC audio stream in a 30-minute container.

## Premium-pass addendum — 2026-08-26

The premium pass implements the two quality safeguards requested after the baseline delivery. These changes are intentionally separate from the verified baseline MP4: the new run creates an entirely new artifact root and never mutates that file.

### What is now implemented

| Requirement | Delivered behavior |
|---|---|
| Make slates loud | Fallback materialization returns an explicit fidelity result. Each fallback job now persists `fallback_kind` (`kenburns`, `slate`, or test-only `synthetic`) and an explanatory detail. The scheduler logs the cumulative logical slate count immediately. |
| Prevent deceptive finalization | Films persist `slate_fraction_limit` (default 5%) and `allow_slates`. When resolved logical slots exceed the slate threshold, the assembler still writes resumable segments but does **not** write the customer-facing final MP4 or mark the film complete. It records `quality_blocked_slates`. A deliberate `--allow-slates` / API approval resumes and finalizes it. |
| Do not retry an image-rate-limit body | `media.download(... expected_content_type_prefix="image/")` classifies a JSON/non-image response, including HTTP 429, as `MediaContentTypeError` before the ordinary retry loop. One definitive non-image response is one request, not three. |
| Scene-not-shot still cache | The cache name is SHA-256 of `stillPrompt`, shared scene seed, output width, and output height—not the output-clip filename. Six camera variants in one scene therefore use one still request. |
| Discovered still budget | Cold still fetches are serialized with a configurable inter-request gap. On the first definitive non-image quota response, remote still fetches stop for that run. Existing retained scene art is deterministically reused for remaining camera variants; only a run with no retained still at all produces a slate. |
| Distinct editorial coverage | `--planner pool` must return strict JSON. For each six-shot scene it must provide one byte-identical `stillPrompt`, one shared `stillSeed`, and six distinct `cameraMove` values. The live video prompt remains individual per shot, so true clips stay distinct. The first shot in every scene is always a persisted `hero_shot`, allowing the 16 scarce true clips to be selected before ordinary coverage. |
| Safe premium operation | CLI now supports `--script-file`, `--plan-only`, explicit chat/video base URLs, provider/seat caps, still-fetch gap, `--slate-fraction-limit`, and `--allow-slates`. A durable plan can be inspected before any live router submission. |

### Verification added for the premium implementation

Focused film-pipeline tests now cover all of the following:

- a 100% slate timeline is visibly recorded and is blocked before final MP4 creation;
- the same durable film finalizes only after explicit slate approval;
- malformed JSON with a valid embedded fragment is still rejected (no permissive parser);
- six scene variants share one still identity/seed and have six different camera moves;
- one image 429 stops further remote still fetches and spreads retained art over later scenes;
- a non-image HTTP response consumes exactly one download attempt.

The focused premium set passed: **6 passed**. The remaining Film Pipeline tests were also run in two bounded groups: **6 passed** and **7 passed**. The FastAPI film route test passed with the expected Pydantic deprecation warning.

### Live router and premium-plan result

The local video router at `http://127.0.0.1:8189/v1/video/capacity` was read successfully after the code change. It reported four `rtst.ai` seats with `clipsRemaining` values **1, 5, 5, 5**—**16 total**. The planned command explicitly uses `--max-clips 16`, `--per-provider-cap 4`, and `--per-seat-cap 1`; the durable store independently prevents a seventeenth submission across a restart.

The premium plan was intentionally attempted in `--plan-only` mode first. It did not reach the video router and submitted **zero** live jobs. The pool returned Markdown-fenced JSON from provider `huggingface-co` for a JSON-only continuity-bible request. Strict parsing rejected it with:

```text
ValueError: planner router returned malformed JSON; this is a router contract failure
```

That is a supply/router issue, not an image, FFmpeg, fallback, or video-capacity failure. Per the instruction for this condition, no lenient parser and no silent local storyboard replacement were added. The premium film should be run only after `:20130` returns an unwrapped JSON body for these JSON-intent requests.

When the router is corrected, the prepared no-extra-credit plan/execution command is:

```powershell
python -m film_pipeline.cli `
  --backend live --live --max-clips 16 `
  --planner pool `
  --per-provider-cap 4 --per-seat-cap 1 `
  --video-base-url http://127.0.0.1:8189 `
  --chat-base-url http://127.0.0.1:20130 `
  --storage backend/run_artifacts/signal_tide_premium `
  --script-file backend/run_artifacts/signal_tide_premium/signal_tide_screenplay.txt `
  --ticks 1000 --tick-sleep 5
```

Leave off `--allow-slates` for the quality-safe default. The run will complete with Ken Burns reuse if image supply reaches a quota wall, and it will stop visibly rather than claim success if unavoidable slates exceed 5% of logical shots.

### Router re-test after `b2d009f`

After the supply-side fence/prose unwrapping change was reported, a direct strict-JSON probe succeeded with an unfenced body from `api-cohere-com`. The premium runner was then retried against the same `:20130` endpoint with no parser change and no slate override.

The retries established three separate facts:

1. The first post-fix planner batch was parseable JSON, but contained 39 objects where the exact contract required 40. The planner was changed to use scene-aligned batches instead of accepting an undersized plan.
2. A four-scene structured batch exceeded the local 45-second transport timeout. The planner was reduced again to the smallest coherent transaction: one six-shot scene per request. This preserves the scene-shared-still contract and avoids any JSON leniency.
3. During the one-scene run, multiple strict responses were accepted, but a later response was genuinely malformed and the strict parser stopped the run. This is the intended loud failure path for real garbage.

At the final check the premium artifact database contained exactly:

```text
films=0, jobs=0, remote_jobs=0
```

Therefore there is no meaningful slate fraction to report: it is **not 0% quality**, it is **not applicable because no logical film timeline was admitted**. The film neither finalized nor reached `quality_blocked_slates`; it was blocked safely at planner-contract validation before any motion clip could be charged.

The committed source-only follow-up is `b39f62d0` (`fix(film): bound planner batches to one scene`). `backend/run_artifacts/` remains ignored and was never staged.

### Provider-independent product increment — 2026-08-27

The following work was completed without consuming a router, chat, image, or video provider resource:

| Item | Delivered behavior |
|---|---|
| Durable character-reference relay | The film API and `FilmRequest` now accept an approved character-reference manifest. It supports the documented `sheetUrl` / `portraitUrls` form (and simple URL lists), persists the normalized manifest in the film continuity bible, and merges those references into **every** planned shot. A chat planner may add references but cannot erase approved character sheets by returning an empty `imageRefs` array. |
| Strict planner fault attribution | The parser remains strict, but any JSON-contract error now names the supplying planner provider/seat when the router supplied one. This gives the router owner an actionable failure identity without relaxing or repairing the content. |
| Resume-at-200-of-360 proof | A new durable integration test checkpoints 200 materialized slots and three 60-shot segments, reconstructs a worker, and proves that only slots 201–360 are materialized. It then completes the final six segments without re-rendering the checkpointed coverage. |

Verification for this increment: **8 focused Film Pipeline/API tests passed**, including character-reference relay, named strict-parser failures, API compatibility, safety-cap behavior, and the 200-of-360 restart path. It was committed source-only as `68309823` (`feat(film): persist character references and resume proof`).

This completes the **relay** portion of character continuity. Generating controlled character-sheet images remains a separate upstream/crew-artifact task; the durable film path now has a correct place to persist and consume those URLs once supplied.

## Delivered implementation

### 1. Hybrid completion path — P0 #0

The router is now a quality lever, not a completion gate.

When a router submission returns `503 {error: "no_capacity"}`, the logical shot changes to `fallback_pending`. The scheduler renders a local MP4 in the exact same canonical job slot. When a polled router job fails with `wall:`, the same local fallback path is used.

The fallback chain is:

1. Reuse an approved HTTP image reference when a shot has one.
2. Otherwise generate a Pollinations still image without an API key.
3. Turn the still into an FFmpeg Ken Burns MP4 with the requested timing and aspect ratio.
4. If the still service itself is unavailable, generate a timed slate MP4 instead of leaving an unfillable assembly gap.

Every fallback clip becomes a normal local `succeeded` job. The incremental assembler therefore remains ordered and does not need an outage-specific branch.

Primary code:

- `backend/film_pipeline/assembly.py` — `FallbackClipMaterializer`, `KenBurnsFallbackMaterializer`, and test-only synthetic fallback.
- `backend/film_pipeline/orchestrator.py` — fallback scheduling/materialization in `tick`.
- `backend/film_pipeline/store.py` — `fallback_pending`, fallback provenance, and cost reporting.

### 2. Durable clip graph safety — P0 #1 through #5

| Issue | Delivered behavior |
|---|---|
| No terminal film failure | `quarantined` and remaining terminal non-fallback jobs mark the film `failed`; future ticks short-circuit. |
| Dedup inert because seeds differ per position | Canonical render dedup ignores position-derived seed and gives duplicates the first canonical shot seed. |
| Fuzzy dedup merged distinct actions | Only byte-identical canonical payloads can reuse a render. Prompt wording, image-reference order, and duration remain meaningful. |
| Concurrent scheduler ticks can double-submit | A SQLite `BEGIN IMMEDIATE` conditional claim persists `submitting` before the router `POST`; only the winner may submit. |
| Crash after film row creation leaves zero-shot replay stuck | Idempotent replay detects the zero-shot state and completes planning/persisting the graph. |

Claims that survive a worker crash are also recovered conservatively. Re-submission uses the same durable router `jobKey`, which remains protected by the frozen idempotency contract.

### 3. P1 scheduler resilience

| Issue | Delivered behavior |
|---|---|
| Auth failure affects all seats | The failed assigned seat is marked unavailable locally; the film slot completes through the local fallback rather than globally blocking the film. |
| Poll/capacity HTTP errors crash ticks | All non-2xx poll and capacity responses map to transient router errors handled inside the scheduler. |
| Poll transport error spends render attempt budget | Poll errors only update poll metadata; they do not increment submission attempts or trigger a re-POST. |
| `refused_safety_cap` reverts to `running` | It is a terminal short-circuit state alongside `refused_capacity`. |

### 4. In-flight concurrency and hero-shot ordering

The scheduler claims all permitted jobs first and then performs the allowed router `POST`s concurrently. Provider and seat caps apply to both durable inflight rows and local reservations made during the current tick.

`ShotSpec.hero_shot` is persisted, and the due-job query prioritizes canonical jobs referenced by a Director-marked hero shot. This reserves scarce real motion capacity for the most important shots rather than spending it FIFO on early coverage.

### 5. Audio delivery

The durable path now creates a local procedural Sound Director score and passes it to final muxing. A short score is looped over the entire final runtime so it produces a real AAC track without depending on a music API or a 30-minute pre-rendered score.

### 6. Storyboard Artist is a real crew stage

`AgentType.STORYBOARD_ARTIST` was missing even though related models and UI references already existed. It has been restored as a typed agent role and abstract orchestration method.

The legacy crew execution now invokes the Storyboard Artist after Scene Designer, passes approved storyboard panels to Animator, includes storyboard context in Director review, returns the storyboard artifact, and supports storyboard retries.

## Verification evidence

Focused implementation verification passed:

```text
77 passed, 109 Pydantic deprecation warnings
```

The added multi-lane submit test also passed:

```text
1 passed
```

Total relevant checks: **78 passing**.

Covered scenarios include:

- router idempotency and exhaustion;
- zero-seat fallback completion and ordered final assembly;
- restart after worker loss without duplicate generation;
- exact dedup and no fuzzy action merge;
- zero-shot crash recovery;
- atomic claims under two simultaneous ticks;
- terminal film failure;
- seat-local auth handling plus fallback completion;
- non-2xx poll/capacity behavior;
- poll errors without submission-attempt inflation;
- persistent safety-cap refusal;
- 360-shot planning and idempotent replay;
- three independent provider lanes submitting in one tick;
- corrected crew contracts and storyboard hand-off.

The official `video_jobs_face.py --selftest` harness was not run. It is not available in the oioi workspace or on the machine command path. Per the ownership boundary, no external supply repository was opened, imported, or modified. The contract-faithful local mock was used for zero-credit test coverage.

## How the delivered film was produced

The deliverable was made using the new explicit no-seat operator mode:

```powershell
python -m film_pipeline.cli `
  --backend fallback `
  --planner mock `
  --script "Signal Tide: ..." `
  --target-seconds 1800 `
  --storage ".\run_artifacts\signal_tide_30m"
```

`--backend fallback` intentionally exposes no router capacity. It proves that zero capacity still yields a finished MP4 with audio.

The `--planner pool` option uses `http://127.0.0.1:20130` for creative planning. The planner was hardened so malformed or undersized JSON from a chat provider cannot abort the long-film job: it creates a continuity-preserving local storyboard batch with explicit fallback provenance instead.

## Important quality qualification

The final file has 360 real ordered timeline slots, but this deadline render used the deterministic mock planner. That planner deliberately repeats four byte-identical canonical beats so the deduplication safety path can be proven. The final film therefore has four keyless Ken Burns source renders safely reused over its 360 timeline slots.

This proves duration, assembly, audio, zero-capacity completion, graph durability, and zero spend. It is not a premium 360-unique-shot creative cut.

## Remaining work to fully close the product vision

### A. Produce the premium 360-unique-shot visual pass

Run the same path with `--planner pool` and a full screenplay. The now-hardened planner can create distinct ordered prompts and the fallback renderer can produce a distinct local clip for each canonical shot. This is a quality/runtime pass, not an architecture blocker.

### B. Join the seven-stage crew to the durable FilmJobStore pipeline

The legacy crew now executes all seven worker stages plus Director coordination, but the durable long-form Film Pipeline still uses its own continuity-bible/storyboard decomposition route.

Required implementation:

1. Persist every crew output as a durable film artifact.
2. Make Director approval emit the ordered `ShotSpec` list, `heroShot` ranking, and audio cue plan.
3. Make Animator create durable asynchronous clip jobs rather than use the legacy synchronous video path.
4. Feed the approved storyboard directly into the durable scheduler.
5. Keep the deterministic `jobKey` and never use the old synchronous `/v1/videos` route as the long-film execution path.

### C. Add durable character-reference relay

Current character output is principally text, so providers may reinvent the character between shots. Generate a controlled character sheet and portrait references once, persist them, and feed ordered URLs into every relevant `ShotSpec.image_refs` array.

Suggested durable shape:

```json
{
  "characterRefs": {
    "mara": {
      "sheetUrl": "https://controlled-host/characters/mara-sheet.png",
      "portraitUrls": [
        "https://controlled-host/characters/mara-front.png",
        "https://controlled-host/characters/mara-profile.png"
      ]
    }
  }
}
```

### D. Contract addition required for true router cross-seat `auth:` retry

The current frozen contract does not let the consumer reroute a stable terminally failed `jobKey` to another seat. A repeated `POST` returns the same failed job, and there is no seat hint/exclusion/requeue operation.

The implemented behavior is safe and completes the film: mark only the failed seat unavailable and locally fall back that one slot.

To achieve a true router retry elsewhere, the supply contract needs one of:

1. Router-owned automatic reroute of `auth:` jobs under the same logical job/idempotency group.
2. `POST /v1/video/jobs/{jobId}/requeue`, with a guarantee that it preserves idempotency and cannot double-charge.
3. A retry operation with `excludeSeats`, again preserving the original job group and spend accounting.

### E. Wire voice-over and scene-specific SFX

The output now has an actual background score. The next Sound Director increment is to persist voice-over text and timed SFX cues, synthesize narration, then feed narration/music/cues through the existing final audio mixer.

### F. Add an exact resume-at-200-of-360 test

The durable graph, post-submit worker restart, and 360-shot idempotent replay are verified. The remaining targeted test should checkpoint 200 physical local clips, reconstruct the worker, and prove that only slots 201–360 are materialized before final assembly.

## Non-film test note

The broad `backend/tests/test_smoke.py` suite still has unrelated failures involving a missing `/healthz` route, model catalogue entries without `name`, and stale preview-image domain expectations. These were not changed during this focused film delivery because they do not affect the film pipeline or final MP4.

## Files materially changed

- `backend/film_pipeline/assembly.py`
- `backend/film_pipeline/orchestrator.py`
- `backend/film_pipeline/store.py`
- `backend/film_pipeline/shots.py`
- `backend/film_pipeline/clients.py`
- `backend/film_pipeline/mock.py`
- `backend/film_pipeline/models.py`
- `backend/film_pipeline/cli.py`
- `backend/agent_contracts.py`
- `backend/app/services/orchestrator.py`
- Film and crew test files under `backend/tests/`

## 2026-08-27 — provider-independent closure pass

This addendum supersedes the earlier remaining-work entries **B**, **E**, **F**, and
the non-film smoke note above. It was implemented without a live image, video, or
paid voice-generation call.

### Completed: approved crew package → durable film graph

`backend/film_pipeline/crew.py` now provides the explicit hand-off boundary:

1. It requires outputs from Scriptwriter, Art Director, Character Designer, Scene
   Designer, Storyboard Artist, Animator, Sound Director, and Director.
2. It refuses admission unless `director.approved` is exactly `true`; requested
   revisions are returned as the reason, and no film graph is created.
3. It stores the entire approved, typed creative package in the film's durable
   continuity bible: screenplay, art direction/palette, character-design notes,
   scene design, panels, animation plan, voice-over, scene-timed effects, and final
   director notes.
4. It converts scene-labelled SFX into absolute, bounded timeline events and retains
   the caller-supplied character-sheet/portrait URLs as durable reference inputs.
5. `ShotListPlanner` recognizes this approved crew package and expands it directly
   into five-second `ShotSpec` render slots locally. It does **not** call the planner
   provider again for a second storyboard. Each slot records the approved panel and
   animation plan in its continuity object, gets scene-shared still identity and a
   distinct camera move, and retains the hero shot for the first beat of each scene.

`AnimationAgentOrchestrator` now accepts an optional injected `FilmOrchestrator`.
With that explicit dependency, a fully approved crew run calls the hand-off and
persists the graph. Without it, the response truthfully says `film_handoff:
not_configured`; an unapproved Director response reports `not_approved` and cannot
spend or schedule render work. This preserves backwards compatibility while making
the production connection deliberate.

### Completed: narration, local Foley, and final mix

The durable film scheduler now rebuilds its audio plan from the persisted bible on
every worker start:

- voice-over is synthesized via local Windows SAPI when available, otherwise a valid
  local silent timing track; the film fallback explicitly disables public keyless TTS,
  so screenplay text is not sent to an external endpoint;
- scene-specific SFX are rendered from a fixed safe FFmpeg tone/noise vocabulary
  (rain/wind, rumble, chime/servo, impact, generic Foley), positioned at persisted
  timeline offsets; arbitrary crew text is never inserted into an FFmpeg command;
- the existing procedural score remains present, and final assembly now mixes
  narration, ducked music, and the Foley bed into AAC audio.

Audio artifacts live under the film's durable artifact root and use stable filenames,
so an interrupted worker finds and reuses them rather than producing a different plan.
A premium TTS/SFX provider may later replace these local assets for higher fidelity,
but it is no longer required for a playable, narrated-and-scored delivery.

### Completed: unrelated broad smoke defects

- `/healthz` is now an alias of the existing health handler.
- Every model registry entry has a customer-readable `name`; generated inventory
  entries receive a deterministic title from their stable ID.
- Style `previewUrl` values now use `https://image.pollinations.ai/prompt/...`, the
  current image endpoint, instead of stale preview paths.

### Verification performed

All checks were local and zero-credit:

- The original focused Film Pipeline selection passed **7 tests**. A final
  provider-free direct-storyboard test was then added for a 30-second approved scene:
  `pytest -q backend/tests/test_film_pipeline.py -k 'crew_handoff or
  long_approved_scene or local_scene_timed_sfx'` → **4 passed**.
- The new actual FFmpeg SFX test created a two-second scene-timed AAC track and
  verified that it is playable; it did not use a provider.
- `pytest -q backend/tests/test_smoke.py` → **51 passed, 1 pre-existing Pydantic
  deprecation warning**.
- `python -m compileall -q backend/film_pipeline backend/studio_pipeline/media.py
  backend/app/services/orchestrator.py backend/app/main.py` → passed.
- `git diff --check` → passed (only Windows line-ending warnings from Git).

### What remains after this pass

1. **Controlled character-sheet / portrait creation is deliberately still an asset
   acquisition decision.** The pipeline now faithfully persists and relays approved
   URL references, but it does not invent a likeness. A customer-supplied asset or an
   explicitly selected image provider is needed to create those actual images.
2. **A premium production pass still needs live generation only for premium visuals
   and premium audio quality.** It is not needed for graph creation, local cut
   completion, narration/SFX delivery, test coverage, or smoke-suite correctness.
3. **Router contract work remains supply-side only:** true cross-seat recovery of an
   already-terminal `auth:` job needs a router requeue/exclude-seat capability. The
   consumer correctly falls back locally rather than risking a double charge.
4. **The larger paid multi-tenant/product-security roadmap remains a separate product
   program.** It requires a deliberate production API/storage/auth/billing decision;
   it was not silently folded into this focused film-pipeline implementation.

## 2026-08-27 — provider-independent product-gap closure

The requested local-only closure pass is complete. No live image, video, chat, or
voice provider was contacted.

### Durable production routes and approved references

- Added `POST /api/v1/films/crew-admissions`. It accepts the complete approved
  seven-stage package plus Director approval, validates reference URLs, and creates
  a durable local `FilmJobStore` graph. There is deliberately no `live`, provider,
  seat, or credit parameter on this route.
- Added `POST /api/v1/assets/character-references` for customer-provided PNG, JPEG,
  GIF, and WebP character sheets/portraits. It performs bounded (10 MiB) upload,
  signature validation, generated-ID storage, SHA-256 recording, and returns an
  app-controlled reference URL. It does not call an image provider or trust a client
  filename/path.
- The crew-admission endpoint rejects non-HTTPS externally supplied references and
  caps the reference set at 32 items. It does not fetch caller URLs at admission time.

### Unsafe legacy defaults removed

- Direct legacy video generation and the two legacy animation routes that can submit
  video now return `410 legacy_route_retired` by default. The response points callers
  to `/api/v1/films`; a stale `POST` is never redirected into a billable operation.
- Development-only compatibility requires both `APP_ENV=development` and
  `ENABLE_LEGACY_DEMO_ROUTES=true`. It is opt-in, not a production default.
- The Library no longer enumerates or reveals the absolute path of a sibling router's
  harvest directory by default. Legacy harvest browsing is separately opt-in through
  `ENABLE_LEGACY_HARVEST_ASSETS=true`; app-owned local media remains discoverable.
- Unknown project reads and updates now return `404`; they no longer manufacture a
  "Default Project" or silently upsert an arbitrary identifier.

### Registry and catalog contracts repaired

- Every model record now has `name`, `capabilities`, positive latency estimate,
  non-negative priority, and `enabled` fields.
- Catalogue aliases that did not correspond to registered app adapters are mapped to
  the app's supported local/keyless capability families rather than advertised as
  selectable providers.
- All style records now use one of the UI's eight canonical categories, with preview
  and thumbnail both using the active keyless Pollinations image endpoint.
- `get_style()` now honors its empty-object contract for unknown styles.

### Complete verification

The full `backend/tests` set was executed in three non-overlapping groups because
the FFmpeg-backed film suite exceeds an ordinary command-output window:

| Group | Result |
|---|---:|
| API, smoke, model registry, style registry | 2,045 passed |
| AC-10, crew contracts, legacy agent pipeline, adapters, provider registry | 131 passed, 1 skipped |
| Complete durable Film Pipeline including real local FFmpeg assembly | 26 passed |
| **Total** | **2,202 passed, 1 skipped** |

The only warnings are existing Pydantic v2 migration/deprecation notices. `compileall`
for `backend/app`, `backend/film_pipeline`, and `backend/studio_pipeline` passed, as
did `git diff --check`.

### Remaining boundary, stated precisely

There are no remaining implementation gaps that can be truthfully closed without a
customer asset, an approved external provider, or a separately authorized production
platform program. The only remaining feature-quality work is:

1. Generate premium character sheets/portraits from a specifically approved provider
   or use the new customer-upload path.
2. Run the premium visual pass with the selected live providers and the existing
   hard sixteen-clip/hero-shot safety policy.
3. Add provider/router support for idempotent cross-seat recovery of a terminal
   `auth:` render job; the consumer already falls back locally and cannot safely
   invent that router capability.
4. For a paid multi-tenant public launch, make the separate product decision to add
   real authentication/tenant authorization, PostgreSQL, private object delivery,
   billing/entitlements, and rights/consent operations. Those are not film-pipeline
   gaps and should not be claimed as solved by a local demo API.

## 2026-08-27 — retained 30-minute artifact diagnosis and zero-provider preflight

### Retained artifact identity

The retained 30-minute file is:

```text
backend/run_artifacts/signal_tide_30m/artifacts/
film_634081fc940b4874b42ff1da2f0324e9/final/film.mp4
```

Its media integrity is good:

| Property | Verified value |
|---|---|
| Duration | 1800.139323 seconds (30:00.139) |
| Video | H.264, 1280×720, 24 fps |
| Audio | AAC, 44.1 kHz, stereo |
| Size | 91,984,983 bytes |
| SHA-256 | `D5CDFD5BA144E558C6B1D654B6FB97368E3F8881D0354C90E6092059B8A1C447` |

It is a successful, playable **local fallback** film, not a failed media render and
not a provider-generated premium-motion film. Its durable store says:

- status `completed`;
- 360 logical timeline shots, six assembled checkpoints;
- four canonical local Ken Burns jobs, all `succeeded`;
- `capacity_at_admission = 0`;
- no `remote_job_id` or `remote_url` for any job;
- fallback reason `capacity: no eligible video seat` for all four jobs;
- zero real credits spent.

Thus the precise diagnosis is:

1. There was **no failure** of this 30-minute MP4. It completed exactly as the
   explicit `--backend fallback --planner mock` operator mode is designed to do.
2. It is not evidence that 360 premium unique provider clips were made. The mock
   planner deliberately reduced the timeline to four canonical visual beats, and the
   selected fallback mode deliberately ran with no router capacity. That is a
   known, intentional baseline-quality trade-off in the local test/render mode—not a
   provider crash and not a hidden assembly bug.
3. The separately attempted premium run did fail before film admission because the
   chat router supplied malformed JSON to a strict JSON-only planner request. That is
   a router/provider contract failure. The consumer correctly failed loudly, created
   no logical film graph, and submitted no video job; it was not a video-provider or
   FFmpeg failure.

### Zero-provider preflight receipts

Two new isolated artifacts were created under the ignored `backend/run_artifacts/`
tree. No router on `:8189`, chat service on `:20130`, image service, paid voice
service, or live provider was called.

1. **30-minute structural preflight**

   - film ID `film_d1caee3e2e954a66976f65b7d168d243`;
   - target 1800 seconds;
   - 360 logical slots, four deterministic mock canonical jobs;
   - durable status `admitted`, no output by design because it was `--plan-only`;
   - zero real credits spent.

2. **Full local end-to-end preflight**

   - film ID `film_db894079ae794372acd4298a5e18d038`;
   - six logical slots, four in-process mock video jobs, three assembled segments;
   - status `completed` with no slate block or error;
   - output H.264 320×180, 24 fps plus AAC 44.1 kHz stereo;
   - duration 30.069661 seconds;
   - SHA-256 `D1B5B317384446DEFA2B332948DE40A36735F406BF00133F4E9938F0E348822C`.

The mock scheduler reports 120 **mock** credits for the four internal mock jobs.
They are accounting values from the in-process test contract, not router/provider
credits; no external spend took place. The artifact tree is confirmed ignored by
`.gitignore` and was not staged.
