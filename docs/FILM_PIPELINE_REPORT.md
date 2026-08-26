# Film Pipeline Implementation Report

_2026-08-26 — consumption layer only. The preceding Phase 0 study and design is in
[`FILM_PIPELINE_PHASE_0_AND_DESIGN.md`](FILM_PIPELINE_PHASE_0_AND_DESIGN.md)._ 

## Outcome

Implemented a durable, HTTP-contract-only film pipeline under `backend/film_pipeline/`,
FastAPI endpoints under `/api/v1/films`, and an operator CLI
(`python -m film_pipeline.cli`). Mock is the default and has no network dependency on
the video router; it spends no real credits. The new layer does not read, import, copy,
or modify `D:\omniroute-monetizer`.

The worker interface is deliberately a bounded scheduler **tick**, not an unbounded
fan-out. Each tick polls only due work and submits only capacity/cap-limited work.
SQLite stores film, shot, job, failure, credit, and assembly state before the next
network call, so a new worker can continue after a process interruption.

## Delivered components

| Component | Location | Behaviour |
| --- | --- | --- |
| Phase 0 study/design | `docs/FILM_PIPELINE_PHASE_0_AND_DESIGN.md` | Existing state and pre-implementation design. |
| Typed contracts | `backend/film_pipeline/clients.py` | Chat messages/models/health; video submit/status/capacity/cancel. |
| Mock backend | `backend/film_pipeline/mock.py` | Exact video routes with latency, capacity and failure injection. |
| Durable graph | `backend/film_pipeline/store.py` | SQLite WAL, unique job keys, retries, quarantine, costs and segments. |
| Shot planner | `backend/film_pipeline/shots.py` | Batched `pool/auto` plan, continuity bible, cache key and dedup. |
| Scheduler/admission | `backend/film_pipeline/orchestrator.py` | Waves/refusal, provider/seat caps, five-second poll floor and accounting. |
| Assembly | `backend/film_pipeline/assembly.py` | Local clips, fixed contiguous segments, hard-cut transitions, final audio/container. |
| API/CLI | `backend/app/api/v1/endpoints/films.py`, `backend/film_pipeline/cli.py` | Mock-first controls; live safety gates. |
| Tests | `backend/tests/test_film_pipeline.py` | Contract, recovery, capacity, failures, API E2E and live gate. |

## Idempotency, failures, and assembly

The caller calculates `job_key` from normalized prompt, duration, sorted image references, seed, and canonical source-shot index. It is unique in SQLite and sent unchanged to `POST /v1/video/jobs`. Duplicate logical shots point to one canonical job and local clip; reposting returns the existing job rather than starting a render. A deterministic film-request fingerprint means restart/resubmission does not re-decompose or change prompts.

| Failure | Durable state | Response |
| --- | --- | --- |
| Transient transport/ordinary failure | `retry_wait`, then `quarantined` | Exponential backoff; same idempotency key only. |
| `503` / `no_capacity` | `parked_capacity` | Stores router retry time; no tight retry loop. |
| Terminal `wall:`/`auth:` | `parked_wall`; seat unavailable | Never retried on that seat; reported. |

Every film summary reports spent, reserved, projected cost, and provider/provider-seat breakouts. Completed clips are normalized locally and reused for duplicate edit positions. The incremental assembler persists fixed ordered segments (60 in production and 2 in mock E2E), then concatenates completed segments once and muxes optional audio into the final MP4. Its default hard cut is an explicit stable transition and it does not re-encode the entire film on every clip arrival.

## Live-safety controls

Real video submission must pass all three safeguards: (1) CLI requires `--backend live --live --max-clips N`, and API requires `backend="live"`, `live=true`, and `max_clips=N`; (2) a live orchestrator refuses a plan/tick whose durable graph exceeds that cap; and (3) a live video client refuses construction without those values and rejects further submits after its own cap. Before its first live tick, the CLI prints provider, admitted clip count, and projected credits. `--backend live --live --max-clips 3` is the appropriate first proof of life and refuses plans over three unique clips.

## Cost model

The following uses the brief's observed 30 credits per five-second clip, 120 credits/account (four clips), and the frozen contract's example 90-second estimate. Wall clock is an inference using the scheduler's default breadth of five providers × one active clip/provider, not a provider promise.

| Case | Unique generations | Credits | Accounts at 4 clips/account | Nominal wall clock |
| --- | ---: | ---: | ---: | ---: |
| Baseline 3-hour film | 2,160 | 64,800 | 540 | 38,880 s = **10 h 48 m** |
| 900 canonical generations | 900 | 27,000 | 225 | 16,200 s = **4 h 30 m** |
| Reduction | 1,260 / **58.33%** | 37,800 / **58.33%** | 315 / **58.33%** | 22,680 s / **6 h 18 m** |

If one provider alone is available, the same 2,160-generation estimate is 54 hours. Admission calls capacity before acceptance and either refuses with a numerical shortfall or stores an explicit capacity-wave plan. Actual cost snapshots use provider values returned after submission; the project-total fallback is 30 credits until observed values exist.

Levers used or deliberately deferred: **shot deduplication is used** (the mock-wave test proves five logical shots collapsed to four canonical renders, or 20%; the 900 row is a target scenario, not an unrun-script claim); **footage reuse is used** (duplicate positions reference one normalized clip); **longer clips are designed but disabled** (the request/key support `durationSeconds`, but five-second beats remain until provider price/support is verified); **re-timing is deferred** (existing ffmpeg helpers need verified source duration/provider semantics); and **cost-per-second selection is blocked by the frozen contract** (capacity exposes no price/second and submit has no provider choice/hint). Breadth across providers is used and observed provider/seat costs are recorded rather than guessed.

## Verification

Ran `PYTHONPATH=backend pytest -q backend/tests/test_film_pipeline.py`: **5 passed** in 7.70 seconds, with one existing Pydantic deprecation warning. The suite covers frozen mock idempotency (`202` then `200`), exhausted capacity, worker reconstruction from SQLite with no duplicate generations, capacity parking, transient vs wall state handling, and full FastAPI mock request → ticks → playable final MP4. The API test also proves that a live request without both safety controls gets HTTP 400.

I also ran the CLI mock E2E: a 15-second, three-shot film completed with two incremental segments, a playable final MP4, and 90 **mock** credits. These counters are test data only; no real router was contacted.

## Not verified / explicit blockers

- **No real three-clip film was run.** The brief says this video contract is not yet implemented, and real generation requires an explicit capped live invocation. I did not spend credits or call the port-8189 supply router. When the supply layer is ready, an operator must expressly authorize `--backend live --live --max-clips 3` and inspect returned cost/URLs.
- **No live chat-pool call was made.** `ChatPoolClient` implements `pool/auto`; deterministic mock chat keeps CI zero-credit and network-independent.
- The recovery test simulates the relevant boundary: the worker is discarded/recreated from SQLite while the external mock router remains alive. It is not a literal OS `kill -9`, because this Windows test uses an in-process ASGI mock rather than a separately surviving server.

## Frozen-contract concerns

The code follows the contract without changing it, but two omissions prevent complete seat-safe recovery: (1) submission/status report provider but not the chosen **seat**, and there is no `seatHint`; the scheduler can make a conservative client-side capacity assignment but cannot verify the router used it. A returned `seat` plus routing hint would make seat caps and wall reassignment auditable. (2) A failed stable `jobKey` has no retry/reassign operation. Reposting correctly returns the old failed job, so it cannot move a wall failure to another seat. This build parks it rather than risks a duplicate spend. A server-side reassign/retry retaining idempotency lineage would close that gap.
