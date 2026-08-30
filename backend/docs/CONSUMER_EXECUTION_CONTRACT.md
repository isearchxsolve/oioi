# OiiOii Consumer Execution Contract

## Production invariant

Customer filmmaking has one execution lineage:

```text
authenticated /api/v1/films/crew-runs
  -> AnimationAgentOrchestrator with ChatPoolClient
  -> http://127.0.0.1:8190/v1/chat/completions (session-pool/auto)
  -> Director-approved durable FilmJobStore admission
  -> authenticated /api/v1/films/{film_id}/tick
  -> VideoRouterClient through the same consumer origin (video/auto)
```

The crew-run operation records a plan only. Rendering is a separately explicit,
ownership-checked scheduler action; live rendering still requires the existing
positive clip cap and explicit live safety switch.

## Retired routes

The old project pipeline and direct image/audio/video generation routes are
retired by default. Customer chat remains available, but is a thin
`ChatPoolClient` call to `session-pool/auto` rather than an in-process provider
registry call. Retired routes may execute only under the explicit local
development demo switch already defined by `require_legacy_demo_mode()` and
must never be part of production certification.

The obsolete `studio_pipeline` CLI is also quarantined: it cannot construct its
old `:20128` client in production and requires an explicit local development
opt-in (`OIOI_ENABLE_LEGACY_STUDIO_PIPELINE=true`) for historical diagnostics.

## Access control

There is no public `/media` static mount. Final films and managed character
references are returned only by owner-authorized API handlers. The durable film
store remains the authority for ownership, audit, history, and artifact metadata.
