# OiiOii live 3-minute E2E report — 2026-08-28

## Result

The provider-dependent 3-minute delivery is **not marked complete**. OiiOii did
not create a completed row, did not calculate a fabricated slate fraction, and did
not retry any video request whose remote spend state is unknown.

The application-side rewire and the provider-free delivery path are complete and
verified. The remaining blocker is the `:8190` consumer service returning neither
the strict planning JSON nor a video-submission receipt required to safely continue
an actual paid render.

## Consumer observations

| Check | Observed result | Outcome |
| --- | --- | --- |
| `GET http://127.0.0.1:8190/v1/models` | HTTP 200; current response contained 51 total models and 24 concrete `video/<host>/auto` records after excluding generic `video/auto` | Healthy non-spending discovery; seat count is correct for the configured cap. |
| Pool planner preflight | `www.meta.ai` returned non-JSON to a JSON-only continuity-bible request | Strict parser rejected it; **no video call** was made. |
| Second pool-planner attempt | `api.monica.im` returned non-JSON to the first JSON-only shot batch | Strict parser rejected it; **no video call** was made. |
| Live video diagnostic | Four `video/auto` POSTs received no response within the 180-second receipt budget | Remote render/spend status is unknown. OiiOii quarantined the attempts and did not repost them. |

The four diagnostic attempt keys remain in the ignored local diagnostic database
under `backend/run_artifacts/live_3m_consumer_render_actual/`. They have no remote
job ID, URL, or final artifact. They are not a successful film and must not be
represented as one. A provider operator should reconcile them from its own request
logs before any manual retry.

## Application work completed

- Rewired live chat and video clients to `:8190/v1` and its OpenAI-shaped
  `/v1/chat/completions` request/response envelope.
- Preserved router `provider`, `session`, and `tenant` in durable clip job records.
- Reads the concrete seat catalogue, excludes the `video/auto` alias, exposes the
  observed 24 dispatchable seats, and supports an intentional
  `video/labs.google/auto` pin through `FILM_PIPELINE_VIDEO_MODEL` or `--video-model`.
- Uses a 180-second read budget for large strict-JSON planning responses and video
  submission receipts; parsing remains strict.
- Persists an inline completed video receipt immediately, so an API scheduler tick
  can survive client-process teardown when the bridge returns a final URL directly.
- Corrected a CLI defect where `--planner mock` was ignored for a live-video run.
- Corrected the deterministic local planner so each five-second editorial beat is a
  distinct motion prompt, while six related shots share each scene's still prompt
  and have distinct camera moves.
- Added an ambiguity guard: a video POST transport timeout is a
  `VideoSubmissionUnknown`, not a retryable transient error. The durable job is
  quarantined so an automatic replay cannot purchase a duplicate clip.
- Implemented final-delivery compression (H.264 CRF 28/AAC 96k), SHA-256 metadata,
  10 GiB quota accounting, managed database retention, and owner-authorized
  artifact streaming. Only the final delivery is retained; temporary assembly work
  is deleted after a successful archive.
- Added owner-wide customer history APIs and settings UI support for projects,
  metadata artifacts, durable films, final artifacts, and compressed-byte usage.

## Provider-free preflight result

The corrected local planner produced a valid three-minute graph:

| Metric | Value |
| --- | ---: |
| Target duration | 180 seconds |
| Logical five-second shots | 36 |
| Distinct motion jobs | 36 |
| Confirmed live capacity | 24 concrete seats |
| Planned true-motion coverage on a live rerun | 24 clips / 120 seconds |
| Planned local Ken-Burns coverage | 12 clips / 60 seconds |
| Slate policy | Armed; finalization blocks above 5% unless explicitly overridden |

This is the intended hybrid plan: 24 scarce provider clips go to distinct editorial
moments first, and the remaining timed coverage is generated locally. A slate is
not an acceptable substitute unless an operator explicitly enables `--allow-slates`.

## Verified tests

The following provider-free checks passed after the changes:

```text
5 passed, 1 warning in 21.62s
```

That set covers the new `:8190` consumer contract including a pinned video model,
lost video receipt handling, the FastAPI mock film E2E with database artifact
retrieval, and owner-controlled authentication/history behavior. A separate local
three-minute plan-only run confirmed 36 logical and 36 unique planned shots with
zero provider spend.

## Required provider fixes before the final live rerun

1. **Strict JSON routing:** for JSON-intent `session-pool/auto` requests, do not
   dispatch to seats that return prose/empty/non-JSON bodies. The two observed
   failures were `www.meta.ai` and `api.monica.im`.
2. **Video receipt contract:** document and return a prompt receipt immediately for
   `video/auto`/pinned-video requests. The receipt needs a durable `job_id`, status,
   provider/session/tenant, and either a final URL or a documented status URL.
3. **Reconciliation/idempotency:** accept a durable idempotency key and provide a
   status lookup keyed by it. Without this, an HTTP timeout after POST cannot be
   safely retried by any billing-conscious client.
4. **Cancellation semantics:** if a provider job can be cancelled, publish that
   route and its billing effect. OiiOii intentionally will not claim cancellation
   merely by dropping a local handle.

## Exact rerun gate

After items 1–3 are verified live, rerun with the slate gate still armed:

```powershell
python -m film_pipeline.cli `
  --script-file backend/run_artifacts/live_3m_consumer/brief.txt `
  --target-seconds 180 --backend live --planner mock --live --max-clips 24 `
  --per-provider-cap 4 --per-seat-cap 1 --submit-concurrency 24 `
  --ticks 36 --tick-sleep 5
```

Use `--planner pool` only after the strict-JSON provider fix is confirmed. A
successful rerun must report the final status and actual slate fraction; it must not
be inferred from admission or capacity alone.
