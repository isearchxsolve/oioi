# CODEX HANDOVER — oioi film kit

**From:** the supply side (`D:\omniroute-monetizer`) — harness, chat pool, video pool, `:8189` contract.
**To:** Codex, owner of **all** of oioi.
**Date:** 2026-08-26.
**Read with:** `FILM_PIPELINE_FIX_BRIEF.md` (same folder) — it holds the 9 defects with repros. This file
is the *why*, the *definition of done*, and the *gaps beyond those 9*.

---

## 0. Ownership — no ambiguity

**You own all of oioi**: `backend/film_pipeline`, `backend/agent_pipeline`, the frontend, the DB.
**I own** `D:\omniroute-monetizer` (chat pool, video pool, harness) **and the `:8189` contract spec**.

The two repos meet at **exactly two HTTP surfaces** and nowhere else:

| surface | port | shape |
|---|---|---|
| chat | `20130` | `POST /v1/messages` (Anthropic-shaped), `pool/auto` |
| video | `8189` | `POST /v1/video/jobs` async (below) |

Do not import from `omniroute-monetizer`. Do not point at `/v1/videos/generations` — that is the old
synchronous shape, a different engine, and it is not the supply path. If you need the contract
**changed**, say so; don't work around it.

**These two tracks run in parallel.** Your fixes do not depend on my seat count, and my seat count does
not depend on your fixes. Start now.

---

## 1. The `:8189` contract (frozen — I built the face *from* your `clients.py`, so it is byte-exact)

```
POST /v1/video/jobs
  body {jobKey, prompt, durationSeconds, imageRefs, aspectRatio, seed}
  202 -> new job     {jobId, provider, estimatedSeconds, creditsReserved}
  200 -> idempotent replay of the SAME jobKey (never a second submit, never a second charge)
  503 -> {error:"no_capacity", retryAfterSeconds}

GET  /v1/video/jobs/{id}   -> {jobId, status, provider, progress, url, error, creditsSpent}
GET  /v1/video/capacity    -> {seats:[{seat,provider,creditsRemaining,clipsRemaining,cooldownUntil}],
                               totalClipsAvailable}
DELETE /v1/video/jobs/{id}
GET  /healthz
```

`status` is strictly **`queued | running | succeeded | failed`**. Nothing else ever leaks out.
`url` is a real fetchable URL on the router's own origin (`/v1/video/jobs/{id}/content`), so
`HttpClipMaterializer` works unchanged.

**Failure strings ARE the contract:**

| prefix | meaning | your behaviour |
|---|---|---|
| `wall:` | paywall / credits exhausted | **park it. Never retry. Never pay.** |
| `auth:` | that seat's credential is dead | park **that seat only**, retry the clip elsewhere |
| anything else | transient | retry |

`classify_video_failure` already does this correctly — keep it, and keep fix #6 consistent with it.

### Test the whole thing without spending a credit

```bash
python video_jobs_face.py --engine stub --port 8189   # canned engine, no seats, no network
python video_jobs_face.py --selftest                  # hermetic contract checks
```

Stub prompt hooks drive every branch: a prompt containing `FAILAUTH` → `auth:` failure, `FAILWALL` →
`wall:` failure, `FAILTIMEOUT` → transient. Prove fixes #1, #6, #7, #8, #9 against these — no provider,
no credits, no waiting.

### The timeout lesson — do not re-create it

The **synchronous** pipeline already worked end-to-end and really produced video. Its only failure was a
mid-stage **timeout**. Async fixes the HTTP timeout, but *any* ceiling below a real render re-creates the
same bug one layer down (the engine's poll budget was 120s; it is now 1800s).

So: **no aggressive client-side deadline on a video job.** A clip legitimately takes minutes. Poll it,
don't time it out. This is also why fix #8 matters — a slow render must never be charged as a failed one.

---

## 2. What supply actually looks like — MEASURED 2026-08-26, not projected

**Correction, and it is the most important number in this document.** An earlier version of this section
claimed "~600 clips available". That was a *projection* from `providers × seats × free_clips`, and I let
it read as current state. Measured just now:

```
session_pool.py list      -> 28 seats dispatchable; 4 are modality=video and LIVE (was ZERO this morning)
/v1/video/capacity        -> 4 rtst.ai seats: 11 + 30 + 30 + 30 credits
                             {"totalClipsAvailable": 16}          <- was 1 an hour ago
rtst.ai                   -> PROVEN THROUGH :8189 ITSELF (see below); 16 clips of real motion in hand
heygen.com                -> 3 free renders unused, authenticated, NO ADAPTER BUILT
digen / kling / openart   -> needs work / balance request-signed / no capacity
```

**Where the 16 came from, because it changes how you should read the rest of this file.**
`state/seat_readiness.json` records four automation Chrome profiles, each a *different* Google account,
and all four were already signed in to rtst.ai. Only one had ever been harvested. rtst grants 30 free
credits per account and the adapter was already built, so the other three were a token read each, not an
adapter build: 1 clip -> 16 clips in about ten minutes and zero signups. Same trick may repeat on other
providers those profiles are signed in to (akool, digen, magichour, giz, heygen, Google Flow), so
`totalClipsAvailable` can still move tonight. Plan for it to grow, never for it to reach 360.

**The contract is no longer a spec — it is proven against real money.** One clip went the whole way
through the frozen face tonight, 2026-08-26:

```
POST /v1/video/jobs      -> 202 {jobId: daf1a7676753466c82acd3d22113a62d, provider: rtst.ai}
POST again, SAME jobKey  -> 200, SAME jobId          (no second submit)
GET  /v1/video/jobs/{id} -> running x4 -> succeeded  (~50s)
GET  .../content         -> 200, 705,465 bytes, ftypisom = a real MP4
rtst balance 17 -> 11    -> exactly 6 charged for TWO posts: idempotency holds under real money
```

So `jobKey` idempotency, the async poll, the `url`-on-my-own-origin rule that keeps
`HttpClipMaterializer` unchanged, and single-charge semantics are all measured, not asserted. Build
against them with confidence.

**Real motion clips available tonight: 16, measured, in hand. Against 360 needed. ~4.5%.** Better than
the ~1% this document claimed an hour ago, and still nowhere near enough — 360 clips at 5 clips per free
account needs ~72 accounts.

**So read §4.1 again with this in mind: Ken Burns is not a degradation path, it IS the film.** The
`:8189` pool contributes roughly 16 hero shots. Concretely, for your orchestrator:

1. **`503 no_capacity` is still the answer for most shots.** 16 of ~360 render as true motion; the other
   ~344 get the 503. The film must be complete and watchable with zero clips from me.
2. **Spend the real clips deliberately.** Those 16 go to the shots that need true motion — the opening, a
   climax, whatever the Director marks — not to shots 1-16 in submission order. A `heroShot` flag on
   `ShotSpec`, or simply "spend capacity on the first N shots the Director ranks", is enough. Do not let
   FIFO burn the entire motion budget on the title card.
3. **`totalClipsAvailable` moves, is cheap to read, and every clip it reports is real.** It went 1 -> 16
   tonight and may move again. `GET /v1/video/capacity` now answers in **~0.1s** (parallel probes, 45s
   cache, primed at startup), so poll it as often as you like — it is genuinely tick-safe now. It was
   46s at 4 seats before I fixed it, which would have blown a tick budget; if you ever see it slow
   again, that is my bug, tell me.
4. `provider` differs per clip and that is correct. Visual consistency comes from prompt + `imageRefs`
   + `seed`, never from provider affinity.

Breadth is enforced on my side (per-host lock + per-seat cooldown), so keep **many jobs in flight** —
see P0 #0b. That stays true whether capacity is 4 or 400.

---

## 3. Your work — P0 first (detail + repros in `FILM_PIPELINE_FIX_BRIEF.md`)

**P0 — money / correctness**

0. **The hybrid degradation path — do this one FIRST.** Full detail in §4.1. On `503 no_capacity` or a
   shot ending `wall:`, that shot falls back to a keyless Ken Burns clip in the **same ordered slot**
   instead of stalling the film. It is listed ahead of the dedup fix because it is the only item that
   makes the deadline independent of my seat count: with it, a 30-minute film finishes tonight and
   `totalClipsAvailable` merely decides how much of it is true motion. Without it, e2e needs ~360 real
   clips, which 3 Google-SSO seats cannot deliver tonight at any effort. **This is the critical path.**

0b. **Serial submission — measured broken, see §4.3.1.** Your Phase-0 study found the animator
   delegates *one scene at a time* with no durable clip-job graph. 360 shots serially cannot finish
   tonight regardless of supply. Needs a clip-job graph plus a raisable concurrency cap. #0 makes the
   film *possible*; #0b makes it *finish in time*. Neither is optional and neither is a document.

1. **No terminal `failed` state for a film** → a dead clip makes the film un-finalizable, yet `tick`
   re-stamps it `running` forever: infinite re-tick, wasted polls.
2. **Dedup is inert in the default config → you pay for duplicate clips.** `decompose` gives every shot a
   distinct position-derived seed; `deduplicate_shots` only collapses *equal* seeds, so nothing ever
   collapses. **This is the credit-saver and it directly buys film length — highest value item in this
   document.**
3. **Dedup can merge DISTINCT shots** (order-insensitive word-set Jaccard) → wrong render. Merge only on
   byte-identical canonical payloads.
4. **Non-atomic claim** (cap-check → await submit → mark_submitted) → concurrent ticks both submit →
   double-charge. Claim atomically before POST.
5. **Crash between `create_film` and `add_shots_and_jobs` bricks the film** (zero shots, replay never
   re-decomposes).

**P1 — tick resilience**

6. Auth/seat-cred failure kills the clip on **all** seats instead of just the bad seat.
7. A 4xx while polling, or any non-2xx from `capacity()`, is unclassified and **crashes the whole tick**.
8. A transient transport error **while polling** is charged against the render budget → quarantines a
   still-running clip.
9. `tick` short-circuits `refused_capacity` but not `refused_safety_cap` → the refusal gets relabeled
   `running` and its error wiped.

**Confirmed NOT defects — do not "fix" these:** package isolation holds (the one outbound
`media.download()` is the frozen contract); the three live-spend gates are enforced with no bypass (the
CLI `LIVE PLAN … projected_credits` line is an informational receipt, not a gate); `job_key` is
deterministic and `UNIQUE … ON CONFLICT DO NOTHING` — that is the double-charge backstop, keep it as is.

---

## 4. Gaps beyond those 9 — corrected after actually reading your code

**Correction first, because I got this wrong and would have sent you chasing ghosts.** An earlier draft
listed assembly, mixed-provider normalization, audio, and duration mapping as open gaps. They are
**already solved in oioi** — I had not read `film_pipeline/assembly.py` or `studio_pipeline/media.py`
when I wrote that. Verified now:

- **Assembly exists and is incremental + ordered** (`assembly.py`), via `media.concat_copy` with
  `CONCAT_BATCH = 60`.
- **Mixed-provider clips are already normalized before concat.** `HttpClipMaterializer.materialize` does
  `download` → `resolve_size(aspect_ratio)` → `normalize_clip(src, dst, duration, w, h)`, so a 5s 720p24
  clip and an 8s 1080p30 clip stream-copy together cleanly. Closed.
- **Audio is fully solved** — `synthesize_narration` (keyless Google TTS, Windows SAPI fallback),
  `synthesize_music_bed`, `mix_final_audio(narration=, music=, loop_music=True)`. Closed.
- **Duration mismatch is absorbed** by `fit_video_duration` / `fit_audio_duration`. Closed.

Here is what is actually open.

### 4.1 The headline: you do not need my video supply to ship a film

`studio_pipeline/media.py` has `synthesize_kenburns_clip` over `pollinations_image_url` — a real MP4 with
real frames, keyless, free. Your own docstring says the Director's FFmpeg concat "produces a real 3-hour
feature today". So **a 30-minute film is deliverable with zero video credits**, and my `:8189` pool is a
**quality lever, not a gate**. Every framing I gave you that treated credits as the blocker was wrong.

**What I want from you because of this — now promoted to P0 #0 in §3, ahead of the dedup fix:** a
**hybrid degradation path** in the orchestrator. When
`/v1/video/jobs` answers `503 no_capacity`, or a shot ends `wall:`, that shot falls back to a Ken Burns
clip instead of stalling the film — same `ShotSpec`, same slot in the ordered assembly, lower fidelity.
Then the film **always** finishes and `totalClipsAvailable` only decides how much of it is true motion:
spend real clips on the shots that need motion, still the rest. This is the one change that makes the
deadline independent of my seat count.

### 4.2 The cast gap — character consistency (highest-value cross-repo item)

`CharacterDesignerOutput.characters` is **text** (`name`, `description`, `prompt`). `ShotSpec.image_refs`
exists and `:8189` passes it through untouched. But nothing renders a character reference image **once**
and relays that same image into every shot — so each clip re-invents the character's face, on a
different provider each time. That is the difference between a film and 360 unrelated clips.

I have `character_relay.py` on my side (render/upload once, relay into every generator's image slots),
parked. **Tell me the shape you want to send** — one `imageRefs` URL per named character, or a single
character sheet — and I will make the seats accept it. Prompt + `imageRefs` + `seed` is the *only*
consistency mechanism available; there is no provider affinity to lean on.

### 4.3 Still genuinely open — verify and report

1. **In-flight concurrency — NO LONGER OPEN. Your own Phase-0 study measured it and it is broken.**
   `FILM_PIPELINE_PHASE_0_AND_DESIGN.md` records: *"the animator delegates one scene at a time to
   `agent_pipeline.AnimationPipeline.run_animator`; it reports individual clip URLs but has no durable
   clip-job graph."* That is serial submission, and it is the wall-clock killer: 360 shots one at a
   time cannot finish tonight at any provider count. **This is the entire reason the contract is
   async** — parallelising clips so a long film renders in less than its runtime. If the caller still
   waits for each clip, async bought nothing but a different timeout. **Needs: a durable clip-job
   graph plus a concurrency cap you can raise, defaulting to roughly the lane count from
   `/v1/video/capacity`.** Treat this as P0 #0b, beside the Ken Burns fallback.
2. **Scale to 360 shots.** Exercised on short films so far. Does `decompose` → 360 shots → 360 jobs hold
   up (DB, memory, tick duration)? A tick that walks all 360 jobs synchronously every pass will crawl.
3. **Resume.** If the run dies at clip 200 of 360, does re-running resume from the DB or restart? With
   free credits a restart is unaffordable. `jobKey` idempotency protects the submit; confirm the
   orchestrator actually re-uses it on resume instead of re-decomposing.
   **My half is measured and it holds:** I killed the router mid-session and the completed job came
   back intact after restart — same `jobId`, same `succeeded`, same fetchable `url`. So the job store
   is durable across a router restart and a re-POST of a known `jobKey` still returns the original
   job rather than paying twice. Whatever you build on top of that will not lose clips to my process
   dying; only the oioi-side half of resume is still open.
4. **The 30-minute target itself.** 360 shots at 5s. Confirm `decompose` emits ~360 shots for a 30-minute
   script and does not silently cap.
5. **`AgentType` is missing the Storyboard Artist.** `agent_pipeline.AGENT_ROLES` carries the full crew —
   seven working agents plus the Director who coordinates and approves — and matches `page.tsx`'s
   `agentTeam`. But `agent_contracts.AgentType` has only 7 members and **no `STORYBOARD_ARTIST`**, so
   anything keyed by that enum cannot address the storyboard stage. The file header ("7-Agent Animation
   Pipeline", plus an arrow list that omits Storyboard Artist) predates it too. Cheap fix — but if any
   persistence row or UI progress map is keyed on that enum, the stage is invisible where it matters.

---

## 5. Definition of done

1. `python video_jobs_face.py --selftest` green (my side, already 17/17).
2. Your 5 P0 + 4 P1 fixes landed, each proven against `--engine stub` (zero credits).
3. A **short** film end-to-end on real supply: script → 7 stages → N real clips → **one assembled mp4**
   with audio. This is the spine proof; 6-12 clips is enough.
4. Then the 30-minute run, at whatever `totalClipsAvailable` supports on the day.

## 6. What I owe you

- ~~`/v1/video/capacity` reporting **real** per-seat credits and `clipsRemaining`~~ — **DONE tonight.**
  A seat that can read its own balance for free (rtst) now reports true credits and clips; a replay
  seat, which cannot learn its balance without spending, keeps an honest floor of 1. A seat that
  throws while being asked degrades to that floor rather than 500-ing the endpoint — so `capacity()`
  is safe to call on every tick, which is the premise of your fix #7. **And it is fast:** probes run in
  parallel, cached 45s, primed at startup, invalidated only on a real spend — **0.1s**, down from 46s
  once four seats existed. `has_capacity()` also means what it says now: a seat with zero credits left
  no longer counts toward accepting a job, so you get a clean `503` instead of an accepted job that
  later fails `wall:`.
- ~~More providers wired into the pool~~ — **1 -> 16 clips tonight**, and still going.
- Any contract change you need, in the contract, not in a workaround.

Report back: which of the §4 gaps are real, and whether you need the contract touched.
