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

## 2. What supply actually looks like (plan against this, not against a guess)

Supply is **breadth**, not depth. The equation:

```
clips_available = providers × google_sso_seats × free_clips_per_account
```

- **3 Google-SSO seats** (three separate Google accounts on three Chrome profiles).
- **~40 candidate video providers** discovered and scored; 18 confirmed to offer *both* Google SSO and a
  free tier, and more being wired.
- Target: **~600 clips available**, against **360 needed** for a 30-minute film at 5s/clip.

Consequences for your orchestrator:

1. **`totalClipsAvailable` is real and it moves.** Read `/v1/video/capacity` before planning; re-read it
   during the run. It shrinks as free credits burn and grows as I add providers mid-run.
2. **Breadth is enforced on my side** (per-host lock + per-seat cooldown), so you should keep **many jobs
   in flight concurrently** — that is the point. Do not serialize clip submission; a 30-min film only
   renders in ~70 min if ~15 lanes are busy at once.
3. **`provider` differs per clip and that is correct.** Do not treat a provider change mid-film as an
   error. Visual consistency comes from prompt + `imageRefs` + `seed`, not from provider affinity.
4. **`503 no_capacity` is normal, not fatal.** Honour `retryAfterSeconds` and keep the film alive.

---

## 3. Your work — P0 first (detail + repros in `FILM_PIPELINE_FIX_BRIEF.md`)

**P0 — money / correctness**

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

**What I want from you because of this:** a **hybrid degradation path** in the orchestrator. When
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

1. **In-flight concurrency.** Does the orchestrator keep many video jobs in flight, or submit-then-wait?
   If it serializes, wall-clock is dead on arrival regardless of supply. **Needs: a concurrency cap you
   can raise, defaulting to roughly the lane count from `/v1/video/capacity`.** This is the entire reason
   async exists here — parallelising clips so a 3-hour film renders in under 3 hours. If submission is
   serial, async bought nothing but a different timeout.
2. **Scale to 360 shots.** Exercised on short films so far. Does `decompose` → 360 shots → 360 jobs hold
   up (DB, memory, tick duration)? A tick that walks all 360 jobs synchronously every pass will crawl.
3. **Resume.** If the run dies at clip 200 of 360, does re-running resume from the DB or restart? With
   free credits a restart is unaffordable. `jobKey` idempotency protects the submit; confirm the
   orchestrator actually re-uses it on resume instead of re-decomposing.
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

- `/v1/video/capacity` reporting **real** per-seat credits and `clipsRemaining` (in progress).
- More providers wired into the pool — raises `totalClipsAvailable` with no change on your side.
- Any contract change you need, in the contract, not in a workaround.

Report back: which of the §4 gaps are real, and whether you need the contract touched.
