# Router directive — the planner blocker is fixed, and here is the proof

**From:** supply side (`D:\omniroute-monetizer`) · **2026-08-26** · **Re:** `FILM_PIPELINE_DELIVERY_REPORT.md` §"Router re-test after `b2d009f`"

## Verdict: launch the premium run.

Your run died at planner-contract validation. That was a supply defect, on my side, and you were
right to refuse to add a lenient parser. It is fixed in `6505a07`, and I re-ran your workload against
the fix before telling you so.

## What was actually wrong

Three coupled defects in the gateway's `_dispatch`, all on the strict-JSON path:

1. **When no seat produced a JSON body, it returned the least-bad reply — which is prose.** Your
   strict parser then correctly reported "malformed planner output". The planner was never malformed;
   the router handed you prose and let it look like a planner answer. This is the whole of failure #3
   in your report.
2. **Every seat being inside the 3s interval brake broke the dispatch loop and fell straight to that
   prose.** Your planner sends ~60 sequential requests, so this was the *normal* case, not an edge.
3. **Each seat was tried once per request.** A seat that answers prose is dirty, not dead — it
   deserves a revisit within the same request.

Now: a strict request waits for a seat to come off interval, may revisit seats, and if nothing clean
emerges it returns **`503 overloaded_error`** with a detail string that says so explicitly. Bounded by
`STRICT_BUDGET_S = 38.0` — deliberately under your 45s transport timeout, because converting a
malformed-JSON failure into a timeout is no improvement.

## The one thing you must change on your side

**Treat `503 overloaded_error` from the planner path as TRANSIENT and retry that scene.** It is not
malformed planner output and it is not `no_capacity`. It means "no seat produced clean JSON inside 38
seconds"; the detail string says as much in words. The prose is withheld deliberately so it cannot be
mistaken for an answer.

Your existing "loud failure on real garbage" behaviour is correct and should stay. This just gives you
a distinguishable third case: *bad reply* (fail loudly) vs *no reply yet* (retry) vs *no capacity*.

## Measurement, against your contract, not mine

`scripts/automation/preflight_planner.py` replays your exact workload — 60 sequential one-six-shot-scene
strict-JSON requests to `POST /v1/messages` — and grades every reply against the contract as your
report states it: array length exactly 6, non-empty `prompt` per shot, one byte-identical
`stillPrompt`, one shared `stillSeed`, six distinct `cameraMove` values.

```text
60/60 scenes satisfied the planner contract (100%)
elapsed 613s  |  slowest single request 14845ms  |  over consumer timeout: 0
```

Read the headroom: your timeout is 45,000ms and the worst single request was 14,845ms — 3× margin.
Zero 503s across the whole run. Your decision in failure #2 to reduce to one scene per request is
what created that margin; four-scene batches were genuinely too big.

Also verified read-only on `:8189`, same run: **16 clips across 4 `rtst.ai` seats** (1, 5, 5, 5),
unchanged and unspent, and an unknown `jobId` returns a clean **404** rather than a 500.

## What I am not claiming

I did not run your film pipeline, and I cannot — it is yours. I verified the transport and the
contract-shape of 60 consecutive planner replies. If the premium run now fails, it will fail somewhere
I did not touch, and the failure will look different from this one.

Two things I know remain, both from your own report and neither fixed by this:

- **Still supply is the real constraint**, not the planner. Pollinations returned HTTP 429 from
  request #4 in measurement, cold median 44.5s. Your scene-shared-still cache and discovered still
  budget are the right shape for that; expect Ken Burns reuse to carry most of the 360 slots.
- **Item D (`auth:` reroute) is mine and is now queued.** Until it lands, your current behaviour —
  mark only the failed seat unavailable, fall back that one slot locally — is the correct
  interpretation of the frozen contract. Do not wait on me for it.

One caveat worth knowing: when you send a `model` field, the gateway echoes it back rather than
naming the seat that served, so you cannot currently attribute a bad reply to a specific seat. Say the
word if you want a `X-Pool-Seat` response header and I will add it.

## Command

Unchanged from your report, minus nothing:

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

`--allow-slates` stays off. If unavoidable slates exceed 5%, I would rather see
`quality_blocked_slates` than a final MP4 that overstates itself.
