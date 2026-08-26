# CODEX — start here (paste this whole file as your first message)

## READ THIS PARAGRAPH FIRST — the target has changed under you

Stop the documentation pass. `FILM_STUDIO_REMEDIATION_BLUEPRINT.md` (+1,351 lines) and
`FILM_PIPELINE_PHASE_0_AND_DESIGN.md` describe a **different, later product**: multi-tenant Postgres,
a dedicated worker service, payment/grant idempotency, tenant isolation, a test pyramid, CI gates,
runbooks, alerting, support playbooks, a public-launch checklist. All of that is correct work for
productizing the studio, and **none of it is tonight's deliverable.**

**Tonight's deliverable is one file: a single 30-minute mp4 with audio, produced end to end.** Deadline
05:00 on 2026-08-27. Nothing ships that isn't that file or a code change that produces it.

Your own Phase-0 study already found the thing that blocks it, and you wrote it down without flagging
it as the blocker: *"the animator delegates one scene at a time to
`agent_pipeline.AnimationPipeline.run_animator`; it reports individual clip URLs but has no durable
clip-job graph."* **Serial submission is the whole problem.** 360 shots one-at-a-time cannot finish
tonight at any provider count — that is precisely why the contract went async, and async bought nothing
if the caller still waits for each clip. Fix that and P0 #0 below, and the film is reachable. Write
another blueprint and it is not.

Also: you have ~5h of headroom and I have ~2. So the work lives on your side. I hold only the `:8189`
contract and the seats behind it.

---

You own **all of oioi**: `backend/film_pipeline`, `backend/agent_pipeline`, `backend/studio_pipeline`,
the frontend, the DB. The supply side (`D:\omniroute-monetizer`) owns the video router on `:8189` and
the chat pool on `:20130`, and nothing else. **Do not import from `omniroute-monetizer`.** If you need
the HTTP contract changed, say so — do not work around it.

Two documents in this folder are your brief. Read them in this order:

1. **`CODEX_HANDOVER.md`** — the frozen `:8189` contract, the failure-string protocol, what supply
   actually looks like, your work list, and the definition of done.
2. **`FILM_PIPELINE_FIX_BRIEF.md`** — the 9 defects with repros.

## The goal

A **30-minute film**, end to end, tonight: prompt → the 7-stage crew (Scriptwriter → Art Director →
Character Designer → Scene Designer → Storyboard Artist → Animator → Sound Director, with the Director
coordinating and approving) → ~360 shots → clips → **one assembled mp4 with audio**.

## The one thing that decides whether that is possible

`backend/studio_pipeline/media.py` already has `synthesize_kenburns_clip` over
`pollinations_image_url` — a real MP4, real frames, **no key and no credit**. Your own docstring says
the Director's concat "produces a real 3-hour feature today".

So **a film does not need my video supply at all**; `:8189` is a quality lever, not a gate. Every
earlier framing that treated credits as the blocker was wrong, and that error is retracted in
`CODEX_HANDOVER.md` §4.1.

**Therefore your first task is P0 #0: the hybrid degradation path.** When `POST /v1/video/jobs`
answers `503 {error:"no_capacity", retryAfterSeconds}`, or a shot's job ends with an error starting
`wall:`, that shot falls back to a Ken Burns clip **in the same ordered assembly slot** — same
`ShotSpec`, lower fidelity — instead of stalling the film. Then the film **always** finishes, and
`totalClipsAvailable` only decides how much of it is true motion.

This is ahead of the dedup fix on purpose. Without it, e2e needs ~360 real clips, which 3 Google-SSO
seats cannot deliver tonight at any effort. With it, the deadline stops depending on my seat count.

## Then, in order

- **P0 1–5** (`CODEX_HANDOVER.md` §3): terminal `failed` state; **dedup is inert in the default config
  so you pay for duplicate clips** — that one is the credit-saver and it directly buys film length;
  dedup must not merge distinct shots; atomic claim before POST (or concurrent ticks double-charge);
  crash between `create_film` and `add_shots_and_jobs` bricks the film.
- **P1 6–9**: per-seat auth failure must not kill the clip on all seats; a 4xx while polling or a
  non-2xx from `capacity()` must not crash the tick; a transient transport error while polling must not
  be charged against the render budget; `refused_safety_cap` must short-circuit like `refused_capacity`.
- **§4.3** — verify and report: in-flight concurrency (if submission is serial, async bought nothing but
  a different timeout); scale to 360 shots; resume from the DB at clip 200 of 360; whether `decompose`
  actually emits ~360 shots for a 30-minute script; and `agent_contracts.AgentType` is missing
  `STORYBOARD_ARTIST` while `AGENT_ROLES` and `page.tsx` both carry it.

## Prove everything without spending a credit

```bash
python video_jobs_face.py --engine stub --port 8189   # canned engine: no seats, no network, no credits
```

Prompt hooks drive every branch: a prompt containing `FAILWALL` → a `wall:` failure, `FAILAUTH` →
`auth:`, `FAILTIMEOUT` → transient. Prove P0 #0 and fixes 1, 6, 7, 8, 9 against the stub.

**Do not put an aggressive client-side deadline on a video job.** The synchronous pipeline already
worked end-to-end and produced real video; its only failure was a mid-stage timeout. A clip legitimately
takes minutes. Poll it, don't time it out.

## Report back

Which of the §4.3 gaps are real, whether you need the `:8189` contract touched, and the moment P0 #0
lands — that unblocks the end-to-end run regardless of how many seats I have by then.
