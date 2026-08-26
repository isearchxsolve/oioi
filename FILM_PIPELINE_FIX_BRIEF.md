# Film Pipeline — Credit-Safety Fix Brief (for Codex)

**Source:** adversarial 36-agent review of `backend/film_pipeline` (+ its one cross-package dep `studio_pipeline`), 2026-08-26.
**Full per-agent detail (exact repros / line refs):**
`C:\Users\Admin\AppData\Local\Temp\claude\D--omniroute-monetizer\4b6fed74-f98b-4f4d-a367-cc8d0093d280\tasks\w65i8vxp6.output`
and the sibling `journal.jsonl` (one result line per agent).

**Scope:** every fix below is in oioi `backend/film_pipeline` (+ `studio_pipeline`). The review confirmed the
package is correctly isolated — it reaches supply only over HTTP (`:20130` chat, `:8189` video) and imports
nothing from `omniroute-monetizer`. So none of this touches the router; the two repos meet only at the frozen
`:8189 /v1/video/jobs` contract.

---

## Ownership + supply-side handshake (2026-08-26)

**Codex owns all of oioi** — the film kit, `film_pipeline`, `agent_pipeline`, the frontend. The router
repo (`D:\omniroute-monetizer`) and the `:8189` contract spec are not yours to change; if you need the
contract altered, say so rather than editing around it.

**The `:8189` face now exists** (`scripts/automation/video_jobs_face.py`, commit `8b62feb`) and was
built *from* `film_pipeline/clients.py::VideoRouterClient` + `models.py`, so it is byte-exact:
`202` new / `200` idempotent-replay / `503 {error:"no_capacity",retryAfterSeconds}`; status strictly
`queued|running|succeeded|failed`; `url` is a real fetchable URL on the router's own origin
(`/v1/video/jobs/{id}/content`) so `HttpClipMaterializer` is satisfied. **Do not** point at
`/v1/videos/generations` — that is the old synchronous shape, a different engine, and it is not the
supply path.

**Failure strings are the contract.** The face prefixes `"wall:"` (paywall/credits — park it, never
retry, never pay) and `"auth:"` (dead seat credential — park that seat only). Everything else is
transient. `classify_video_failure` already does the right thing — keep it, and keep fix #6 consistent
with it.

**Test without spending anything:** run the face with a canned engine — no live seats, no credits:

    python video_jobs_face.py --engine stub --port 8189
    python video_jobs_face.py --selftest      # 12/12 contract checks, hermetic

Stub prompt hooks exercise every branch: a prompt containing `FAILAUTH` → `auth:` failure,
`FAILWALL` → `wall:` failure, `FAILTIMEOUT` → transient. Use these to prove fixes #1, #6, #7, #8, #9
end-to-end without a provider.

**The timeout lesson — do not re-create it.** The synchronous pipeline *did* work end-to-end; it failed
only on a mid-stage timeout. Async fixes the HTTP timeout, but a ceiling anywhere below a real render
re-creates the bug one layer down (the engine's poll budget was 120s; now 1800s). So: **no aggressive
client-side deadline on a video job.** A clip legitimately takes minutes; poll it, don't time it out.
This is also why fix #8 matters — a slow render must never be charged as a failed render.

**Throughput intent:** every clip is parallelized across *different* providers (breadth, not depth) so a
3-hour film can render in well under 3 hours. Respect the per-seat/per-provider caps and the `>=5s`
poll floor — they are what keep breadth from becoming a burst on one provider.

---

## P0 — money / correctness (do first)

1. **No terminal failure state for a film.** `orchestrator.py` — once any single clip dead-ends
   (quarantined / parked_wall), the film can never pass the "all shots contiguous" finalize test, yet nothing
   marks it failed; `tick` re-stamps it `running` forever → infinite re-tick + wasted polls.
   **Fix:** add a terminal `failed` film state; when a clip is permanently dead, mark the film `failed` with
   the reason and stop ticking it.

2. **Dedup is inert in the default config → you pay for duplicate clips.** `decompose` gives every shot a
   distinct position-derived seed; `deduplicate_shots` only collapses shots with *equal* seeds → with a seed
   set (the default) nothing ever collapses, defeating the credit-saving dedup.
   **Fix:** dedup on the canonical render payload (prompt + image_refs + params), not the seed — or assign
   identical seeds to identical shots before dedup. *This is the credit-saver — it's the lever that cuts
   clips/film.*

3. **Dedup can merge DISTINCT shots → wrong render.** In the `seed=None` path the similarity test is an
   order-insensitive word-set Jaccard: "A hits B" == "B hits A", and prompts differing by one critical word
   collapse into one clip.
   **Fix:** only merge when canonical payloads are byte-identical (exact match / hash); never merge on fuzzy
   word-set overlap.

4. **Non-atomic claim: cap-check → await submit → mark_submitted.** `orchestrator.py` — concurrent ticks can
   both pass the cap check and submit → exceed provider/seat caps and double-submit (double-charge risk).
   **Fix:** atomically claim each job (conditional UPDATE / transaction) before submit; only the tick that
   wins the claim may POST.

5. **Crash between `create_film` and `add_shots_and_jobs` bricks the film.** Two separate transactions; a
   crash in between leaves a film with zero shots/jobs, and the idempotent-replay return path never
   re-decomposes it.
   **Fix:** make create + decompose + add_jobs one transaction, or on replay detect a zero-shot film and
   re-decompose it.

---

## P1 — tick resilience (do next)

6. **Auth/seat-credential failure kills the clip on ALL seats** instead of just the bad seat.
   **Fix:** classify a seat-cred (auth) failure as seat-local → park that seat and retry the clip on another
   seat; don't fail the clip globally.

7. **A 4xx while polling, or any non-2xx from `capacity()`, is unclassified and crashes the whole tick.**
   **Fix:** classify non-2xx poll/capacity responses; degrade (fail the one clip, or honor retry-after) —
   never let one bad response kill the tick.

8. **A transient transport error while POLLING is charged against the render-attempt budget** → can
   quarantine a still-running clip.
   **Fix:** separate poll-transport retries from render attempts; a network blip during polling is not a
   failed render.

9. **`tick` short-circuits `refused_capacity` but not `refused_safety_cap`** → the safety-cap refusal gets
   relabeled `running` and its error wiped.
   **Fix:** short-circuit `refused_safety_cap` the same way; preserve the refusal state + error.

---

## Confirmed NOT defects (recorded so they aren't "fixed" by mistake)

- **Isolation holds.** The single outbound `media.download()` to the result URL the router returns is the
  frozen submit→poll→fetch contract, not a coupling to omniroute-monetizer.
- **The three live-spend gates are ENFORCED, no bypass found** (CLI/API entry switches; orchestrator plan-cap
  + tick-cap; video-client submit cap). The CLI `LIVE PLAN … projected_credits` line is an informational
  receipt, not a gate — that's correct, don't turn it into a blocker.
- **`job_key` is deterministic** (sorted canonical JSON, no time/random/set-order) and **UNIQUE with
  `ON CONFLICT DO NOTHING`** — keep exactly as is; it's the double-charge backstop.
