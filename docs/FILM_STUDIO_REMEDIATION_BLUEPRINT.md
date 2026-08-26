# Film Studio Product Remediation Blueprint

**Status:** implementation plan — no production release approval  
**Prepared:** 2026-08-26  
**Audience:** product owner, technical lead, backend/frontend engineers, QA, operations, and a developer new to the codebase  
**Scope:** turn the current prototype into a secure, durable, paid AI-film studio product. This document includes the findings from the deep audit and the concrete fixes required to close them.

---

## 1. Read this first

### 1.1 Release decision

The current repository is suitable for an **internal prototype and controlled mock demonstration**. It is **not approved for a public paid launch**, and it must not be marketed as a $100 lifetime / unlimited three-hour-film service until the P0 items in this document are complete and independently verified.

The Task 4 film pipeline is a valuable foundation: it has a durable job graph, mock-first execution, capacity-aware dispatch, retries, incremental assembly, and a small passing E2E test suite. It is not yet the whole product. The paid-product, ownership, background-worker, studio-workflow, and user-facing delivery layers are missing or disconnected.

### 1.2 Non-negotiable target behaviour

When this plan is complete, the product must work like this:

1. A customer signs in and purchases (or is granted) a lifetime entitlement.
2. The server records an immutable order/grant and gives that customer a unique durable access URL/token.
3. The customer creates a project, writes/imports a screenplay, and moves through creative approval gates.
4. The customer approves a costed, capacity-admitted shot plan **before** expensive video rendering begins.
5. A background worker, not the browser and not a FastAPI request, advances the film safely after restarts.
6. Every project, input, render job, asset, cost, and final delivery is owned by one tenant/customer and is authorization-checked.
7. The customer can review dailies, change selected shots, build a versioned edit, add sound/captions, pass QC, and receive an authorized delivery.
8. Live spend is controlled by server-side policy and budget. A browser cannot enable an unbounded render or select an arbitrary provider mode.

### 1.3 What this document does and does not authorize

This is a design and implementation blueprint. It does **not** authorize deleting old code, spending live provider credits, changing payment systems, or touching a separate supply-side repository. Make each production migration through code review, backup, staging validation, and an explicit rollout decision.

### 1.4 Terms used consistently below

| Term | Meaning |
| --- | --- |
| **Tenant** | The customer/account that owns data. A single-user customer is still a tenant. |
| **Studio** | Customer-facing name for a tenant; use one canonical database term (`tenant_id` or `studio_id`) consistently, not both on different tables. |
| **Grant** | The durable entitlement created after payment or an administrative issue. |
| **Project** | A customer-owned film workspace. |
| **Film version** | A specific approved production plan and resulting edit/master; projects can have many versions. |
| **Shot** | A creative/editorial position in a sequence. It may have many render attempts and variants. |
| **Render job** | One provider submission for a concrete render specification. |
| **Asset** | An uploaded or generated image, video, audio, script, subtitle, or delivery file. |
| **Dailies** | Reviewable render outputs before final editorial/finishing. |
| **Worker** | A dedicated process that claims and executes durable jobs. It is not an HTTP request handler. |
| **Mock mode** | Test-only synthetic provider path. It must never be presented as customer production footage. |

---

## 2. Findings at a glance

### 2.1 Severity definition

| Severity | Meaning | Release treatment |
| --- | --- | --- |
| **P0** | Could spend money unsafely, expose customer data, lose work, or make the paid offer dishonest. | Fix before public launch. |
| **P1** | Required to deliver a credible, usable studio workflow at feature scale. | Complete before long-form/beta launch. |
| **P2** | Important reliability, quality, maintainability, or scale improvement. | Schedule after P0/P1 baseline, with an owner. |

### 2.2 P0 findings

| ID | Finding | Current evidence | Required outcome |
| --- | --- | --- | --- |
| P0-01 | Legacy routes can still invoke real-credit rendering outside the new safety gate. | `pipeline.py` and `videos.py` describe real credit spend; the current UI uses the legacy project pipeline. | One server-governed live-render path only. |
| P0-02 | No actual authentication, ownership, payment, or entitlement layer exists. | FastAPI auth router is empty; NextAuth credentials always return `null`. | All reads/writes and deliveries are tenant-scoped and entitlement-checked. |
| P0-03 | Project data is process-local and can silently fabricate/overwrite project state. | `_PROJECTS_DB` dictionary, default project fallback, upsert-on-unknown-ID. | Durable database records, strict 404/409 behavior, revisions, and auditability. |
| P0-04 | Assets expose a direct external harvest directory and absolute local paths. | Assets endpoint points at `D:\omniroute-monetizer\state\harvest`, enumerates/streams files. | Private object storage and authorized media delivery only. |
| P0-05 | Film progress requires manual HTTP `tick` calls; no autonomous scheduler exists. | `/films/{id}/tick`; FastAPI lifespan starts no worker. | Durable queue, atomic claims, restart recovery, and customer progress events. |
| P0-06 | The customer UI is disconnected from the new durable film pipeline. | `page.tsx` uses literal `new-project`, no `/films` flow, Export Film has no handler. | Real project/film workflow driven by persisted IDs and status. |
| P0-07 | Mock output can look like a completed customer film. | `/films` defaults to mock and creates playable synthetic MP4s. | Mock is isolated to test/dev; production UI never delivers it as real footage. |
| P0-08 | The new default deduplication claim is false. | Planner increments seeds while dedup requires matching seeds. | Safe, deterministic, explicitly controlled reuse. |
| P0-09 | Worker/backend selection is caller-controlled and not durably bound to a film. | `tick` accepts `backend`, defaulting to mock. | Server derives execution policy from persisted film configuration. |
| P0-10 | Production configuration can fall back to development-style defaults. | Current code permits local/test-style database and configuration paths. | Production must fail closed when required secrets, database, storage, or live-policy configuration is absent. |

### 2.3 P1/P2 findings

| ID | Finding | Required outcome |
| --- | --- | --- |
| P1-01 | No screenplay/version/approval workflow. | Versioned creative artifacts and approval gates before render spend. |
| P1-02 | No hierarchy for act, sequence, scene, shot, take, and final edit. | Studio data model and versioned editorial timeline. |
| P1-03 | Static prompt bible is insufficient for three-hour continuity. | Continuity ledger, scene state, character/wardrobe/location/prop tracking. |
| P1-04 | Basic concat is not editorial/post-production. | Timelines, trims, transitions, audio, captions, color/QC/mastering. |
| P1-05 | No provider spend ledger, quote, or fair-use policy. | Reservation/reconciliation, customer limits, cost controls, transparent ETA. |
| P1-06 | Failed/walled jobs cannot be cleanly re-routed. | Attempt lineage, retry/reassign workflow, human escalation. |
| P1-07 | The browser-dependent long request model is unsuitable. | Async API, events, notifications, resume/review UX. |
| P2-01 | Several applications, databases, and docs conflict. | One authoritative architecture and maintained docs. |
| P2-02 | Frontend test setup is broken and canvas source is malformed. | Parse/type/test clean UI build in CI. |
| P2-03 | Observability, backup, retention, and support tooling are incomplete. | Operations dashboard, audit trail, monitoring, backup/restore procedures. |

### 2.4 Current-code map for the implementer

This table tells a new engineer where each finding lives today. Read the relevant file before changing it. The path is evidence of the current prototype; it is not an instruction to preserve that design.

| Current location | What it does today | Required disposition |
| --- | --- | --- |
| `backend/app/api/v1/endpoints/films.py` | Exposes mock-first film creation and public manual `tick`; accepts caller-controlled backend/live/cap. | Keep its useful orchestration concepts, but move customer commands behind project/tenant/policy APIs and move progression to workers. |
| `backend/film_pipeline/orchestrator.py` | Plans, admits, polls, submits, materializes, and assembles in a bounded `tick`. | Refactor into worker services; add durable claims, policy binding, retry lineage, and tenant-aware models. |
| `backend/film_pipeline/store.py` | Isolated SQLite job graph with global job keys and local cost aggregation. | Use as behavioral reference only; replace/adapt into production SQLAlchemy/PostgreSQL tables and migrations. |
| `backend/film_pipeline/shots.py` | Batches LLM shot planning, increments seeds, and uses fuzzy dedup. | Replace fuzzy reuse with exact tenant-scoped render fingerprints and hierarchical planning. |
| `backend/app/api/v1/endpoints/pipeline.py` | Legacy project pipeline; its own documentation says it can spend real credits. | Disable/deprecate production live use; do not wire it to the new customer flow. |
| `backend/app/api/v1/endpoints/videos.py` | Legacy direct video generation route. | Disable/deprecate customer live use; retain only behind internal service boundary if needed. |
| `backend/app/api/v1/endpoints/projects.py` | Process-local project dictionary, default-project read behavior, upsert-like updates. | Rewrite against tenant-scoped durable project records. |
| `backend/app/api/v1/endpoints/assets.py` | Reads a direct harvest directory and serves discovered files. | Replace with database-indexed, object-storage-backed owned assets. |
| `backend/app/api/v1/endpoints/auth.py` | Empty FastAPI auth router. | Implement or integrate the single selected identity authority. |
| `backend/app/api/v1/endpoints/jobs.py` | Empty route placeholder. | Either remove it or replace it with an authenticated job/status/admin API; do not expose raw worker controls to customers. |
| `backend/app/main.py` | Initializes DB/providers but starts no durable worker. | Keep web lifecycle small; deploy worker as a separate process/service. |
| `src/app/page.tsx` | Current one-page UI, literal `new-project` pipeline calls, fake add-panel state, dead Export button. | Break into authenticated project routes and server-backed feature modules. |
| `src/app/components/Canvas.tsx` | Contains simulated generation and malformed JSX. | Repair + connect to real data only after the project/asset spine works, or exclude from product routes. |
| `src/lib/auth.ts` | NextAuth credential callback always returns `null`. | Replace with a real, unified session implementation. |
| `next.config.js` | Has a very long proxy timeout for synchronous legacy work. | Remove reliance on long browser requests once async command/worker flow exists. |
| `README.md`, `ARCHITECTURE.md`, `backend/README.md`, `PLAN.md`, `DESIGN.md` | Describe partially conflicting products/stacks and stale assumptions. | Reconcile after ADR approval; clearly label legacy code and product limits. |

---

## 3. Architecture decisions to make before coding

Do not begin the fixes as isolated patches. Make these decisions first and write them into `ARCHITECTURE.md` after approval.

### ADR-01 — Choose one production application spine

**Recommended decision:**

```text
Customer browser
  → root Next.js application (`src/`)
  → FastAPI (`backend/app/`) public API
  → PostgreSQL (source of truth)
  → object storage + CDN (private assets/deliveries)
  → worker service(s) (film planning, renders, polling, assembly, QC)
  → provider adapters/router through versioned HTTP contracts
```

Use the root Next.js app as the only customer frontend and FastAPI as the only customer API. Use SQLAlchemy migrations against PostgreSQL as the durable production data model. SQLite may remain for unit tests and local mock runs, but it must not be the public multi-worker source of truth.

**API migration decision:** introduce the safe product API under `/api/v2`. Keep v1 only for explicitly marked legacy compatibility while the migration is in progress. Do not change a legacy POST route into a billable v2 command by redirecting it; request shapes and safety semantics differ.

**Do not delete the other stacks immediately.** First mark `frontend/`, `server/`, and `film-kit-studio/` as legacy/unowned in a short `STATUS.md`; block new feature work there; redirect the active application to the canonical stack; then remove them only after a release and backup plan.

**Acceptance criteria:**

- A new engineer can identify one frontend, one API, one database migration path, one job runner, and one media storage path in under ten minutes.
- Every production route appears in one OpenAPI document.
- No customer UI calls a legacy Express/NIM/direct-harvest route.

### ADR-02 — Make the database authoritative

Use PostgreSQL for production because the product needs transactions, row locks, durable jobs, tenant isolation, audit trails, and multiple workers. Keep SQLAlchemy as the application ORM; introduce Alembic migrations for every schema change.

Do not keep `projects.py`'s in-memory dictionary as a production fallback. Do not use raw filesystem paths as asset identifiers. Every external-facing ID should be an opaque UUID or ULID.

### ADR-03 — Treat the worker as a service, not an endpoint

The API creates commands and reads status. It never spends credits by doing a multi-hour synchronous render. A separately deployed worker claims jobs from the database using leases.

For the first production version, PostgreSQL is enough; use a durable `work_items` table and `SELECT … FOR UPDATE SKIP LOCKED`. Add a dedicated message broker later only when observed load justifies it. This avoids introducing Redis/Celery merely as a second source of truth.

### ADR-04 — Keep supply and consumption boundaries clean

The customer product must use an HTTP/versioned provider boundary or a dedicated internal media service. It must not browse another repository's harvest directory. Render outputs should be copied or streamed into product-owned private object storage, with a stored object key and checksum—not an arbitrary server path.

### ADR-05 — Separate customer intent from execution policy

The browser may request a quality preset (for example `draft`, `standard`, or `premium`) but it must not submit raw `backend`, `live`, `max_clips`, provider-seat, or price-cap values. The server maps a permitted preset and entitlement to a production policy. Only an authenticated internal operator endpoint can enable a live-provider dry run or override an account cap.

---

## 4. P0 remediation playbooks

Each subsection is deliberately procedural. Follow the order inside a subsection; do not merely add a new endpoint while leaving the unsafe one available.

### P0-01 — Retire unsafe live-render entry points

**Problem**

The new film route has explicit live safety controls, but the existing UI calls `/api/v1/projects/new-project/pipeline/scriptwriter` and `/animate`. The legacy pipeline and direct video route can reach real-credit video rendering without sharing the new authorization, budget, and cap model.

**Files involved now**

- `backend/app/api/v1/endpoints/pipeline.py`
- `backend/app/api/v1/endpoints/videos.py`
- `backend/app/api/v1/endpoints/films.py`
- `src/app/page.tsx`
- `backend/app/api/v1/api.py`

**Target design**

There is exactly one customer-facing command for expensive render work:

```http
POST /api/v2/projects/{project_id}/film-versions/{film_version_id}/render
```

This command does not directly call a provider. It validates ownership, grant, approved plan, budget, and policy; then writes one durable `work_items` record. The worker owns all provider submission.

**Implementation steps**

1. Add a configuration flag named `LEGACY_LIVE_GENERATION_ENABLED=false` with a production-safe default.
2. Change legacy live routes so they return a clear `410 Gone` or `503 Service Unavailable` when the flag is false. Do not silently fall back to fake success.
3. Retain the legacy script-only functionality temporarily only if it is explicitly non-spending and authenticated. Put a deprecation response header and telemetry counter on it.
4. Remove the old animation call from the main frontend. Replace it with the new render command after P0-02 through P0-06 are in place.
5. Add a code-level guard: provider submission methods must accept a server-created `SpendAuthorization` record ID. They must reject calls without one.
6. Add an integration test that asserts every legacy render endpoint is blocked in production configuration.
7. After one release cycle with zero legacy requests, delete or archive the legacy live code through a separately reviewed change.

**Pseudo-code**

```python
@router.post("/{project_id}/pipeline/animate")
async def legacy_animate(...):
    if not settings.LEGACY_LIVE_GENERATION_ENABLED:
        raise HTTPException(
            status_code=410,
            detail="This endpoint is retired. Create an approved film version and use /render.",
        )
    # Temporary, authenticated, non-production compatibility path only.
```

**Done when**

- No unauthenticated request can submit a live video job.
- The customer UI contains no calls to `/pipeline/run`, `/pipeline/animate`, or legacy `/videos/generations` for film creation.
- A repository search for provider `submit` calls shows they exist only in the worker/service layer that enforces `SpendAuthorization`.

### P0-02 — Add authentication, ownership, payment grants, and authorization

**Problem**

There is no functioning login on the active API boundary, no account ownership on project/film records, and no lifetime entitlement. The frontend credential provider currently always fails.

**Target database records**

Create migrations for these minimum tables. Use UUID/ULID primary keys, `created_at`, `updated_at`, and soft-deletion/audit fields where noted.

| Table | Minimum important columns | Purpose |
| --- | --- | --- |
| `users` | `id`, `email` unique, `display_name`, `status`, `auth_subject`, `created_at` | Authenticated person. |
| `tenants` | `id`, `name`, `owner_user_id`, `status` | Ownership boundary; one tenant per customer initially is fine. |
| `tenant_members` | `tenant_id`, `user_id`, `role` | Future collaboration without schema rewrite. |
| `orders` | `id`, `tenant_id`, `provider`, `provider_order_id` unique, `amount`, `currency`, `status`, `paid_at` | Payment reconciliation. |
| `entitlement_grants` | `id`, `tenant_id`, `order_id`, `kind`, `status`, `starts_at`, `ends_at nullable`, `policy_json` | Lifetime access and its fair-use policy. |
| `access_links` | `id`, `tenant_id`, `grant_id`, `token_hash`, `scope`, `expires_at nullable`, `revoked_at` | Unique share/lifetime URL; store only a hash of the secret token. |
| `audit_events` | `id`, `tenant_id`, `actor_user_id nullable`, `action`, `resource_type`, `resource_id`, `metadata_json`, `ip`, `created_at` | Security and support evidence. |

**Authentication implementation sequence**

1. Choose one identity approach. The simplest product-safe option is a hosted identity provider or a server-owned OAuth/passwordless flow. Do not maintain raw passwords until there is a clear security owner.
2. In FastAPI, implement a reusable `current_principal` dependency that validates the bearer/session token and returns `user_id`, `tenant_id`, and roles.
3. Implement `require_tenant_role("owner" | "editor" | "viewer")` and use it on **every** project, film, asset, delivery, and billing endpoint.
4. Replace the empty FastAPI auth router with only the routes actually owned by the selected identity model: session exchange, current user, logout/revoke, and secure callback handling. If identity is externally managed, do not build duplicate password endpoints.
5. Make the Next.js session layer talk to the same auth authority. Delete the credentials callback that always returns `null`; do not leave two unrelated auth systems in place.
6. Implement a payment webhook endpoint. Verify the provider signature before parsing the event. Make webhook processing idempotent using the provider event ID.
7. On a verified paid event, create an `orders` record and an active `entitlement_grants` record in one transaction.
8. Generate a random access token only once, show it only at creation, and store `SHA-256(token + server_pepper)` rather than the raw token.
9. Use grant policy checks in the render admission command: active grant, allowed project count/concurrency, maximum target duration, allowed quality preset, and remaining rolling fair-use allowance.

**Authorization rule**

Never load an object by ID alone. Always query by both tenant and ID:

```python
project = session.scalar(
    select(Project).where(Project.id == project_id, Project.tenant_id == principal.tenant_id)
)
if project is None:
    raise HTTPException(status_code=404, detail="Project not found")
```

Return `404`, not `403`, for resources outside the caller's tenant so the API does not disclose which IDs exist.

**Done when**

- A request without authentication receives `401`.
- A valid user from tenant A cannot list, read, modify, render, or download tenant B's data.
- A payment webhook replay produces one order/grant, not duplicates.
- Revoking a grant immediately blocks new renders and protected delivery links.
- A one-time access-link token is never stored in plaintext and can be revoked.

### P0-03 — Replace process-local project state with durable records

**Problem**

`_PROJECTS_DB` disappears on restart. Unknown project IDs produce a fake default project or are silently created by `PUT`. This creates phantom work and masks bugs.

**Target project schema**

| Table | Key fields |
| --- | --- |
| `projects` | `id`, `tenant_id`, `title`, `description`, `aspect_ratio`, `status`, `current_script_version_id`, `current_film_version_id`, `created_by`, timestamps |
| `project_revisions` | `id`, `project_id`, `revision_number`, `kind`, `payload_json`, `created_by`, `created_at` |
| `scripts` | `id`, `project_id`, `version_number`, `source`, `format`, `content`, `status`, `locked_at`, `approved_at` |
| `project_activity` | `id`, `project_id`, `actor_id`, `event_type`, `payload_json`, timestamp |

**Implementation steps**

1. Inspect the existing SQLAlchemy `Project` and `Asset` models. Extend/migrate them rather than adding another incompatible project representation.
2. Add `tenant_id NOT NULL` to projects and backfill only known development records into a development tenant. Do not guess ownership in production.
3. Rewrite `POST /projects`, `GET /projects`, `GET /projects/{id}`, and `PATCH /projects/{id}` to use a database session and `current_principal`.
4. Use `PATCH`, not arbitrary `PUT`, for editable fields. Require an `If-Match` version or integer `revision` for concurrent edits. Return `409 Conflict` when it is stale.
5. Unknown IDs must return `404`. Never create a default project during a read. Never create a project during an update.
6. Save canvas/timeline state as a revisioned document associated with a real project, not a free-floating in-memory object.
7. Write an audit event for create, rename, script lock, approval, render request, cancellation, asset delete, and delivery share.

**Done when**

- Restarting the API preserves all projects and links to their film versions.
- Invalid project IDs give `404` in both API and UI.
- Concurrent project updates do not silently overwrite each other.
- The project list only returns records owned by the active tenant.

### P0-04 — Replace direct harvest browsing with secure media storage

**Problem**

The current assets endpoint reads a separate harvest tree and reveals physical paths. That makes customer data isolation and retention impossible to enforce reliably.

**Target asset model**

| Table | Minimum fields |
| --- | --- |
| `assets` | `id`, `tenant_id`, `project_id nullable`, `kind`, `storage_key`, `content_type`, `bytes`, `sha256`, `duration_ms`, `width`, `height`, `status`, `created_by`, timestamps |
| `asset_versions` | `id`, `asset_id`, `version_number`, `storage_key`, `metadata_json`, `created_at` |
| `asset_permissions` | `asset_id`, `principal_type`, `principal_id`, `scope` | Optional for future sharing. |
| `media_exports` | `id`, `film_version_id`, `asset_id`, `delivery_kind`, `qc_status`, `expires_at nullable` | Delivery/master linkage. |

**Implementation steps**

1. Create a storage interface with methods `put_stream`, `get_signed_read_url`, `delete`, and `stat`. Implement local storage for development and S3-compatible private storage for production.
2. Store only a logical `storage_key`, such as `tenant/{tenant_id}/project/{project_id}/asset/{asset_id}/source.mp4`. Never store an absolute Windows path in API responses.
3. Replace recursive directory enumeration with database queries scoped to `tenant_id`.
4. Create authenticated upload flow: API creates a pending asset/upload record; client uploads with a short-lived signed URL or streams to the API; a worker validates MIME type, size, checksum, duration, and virus/content-scanning policy before marking it ready.
5. On provider completion, the worker downloads the output once, validates it, writes it to product storage, calculates checksum/duration, and creates/updates an owned asset record.
6. Deliver media by a short-lived signed URL or an authenticated streaming endpoint. Re-check tenant/grant before issuing the URL.
7. Add retention state (`active`, `pending_delete`, `deleted`) and a deletion job. A deletion must remove both database access and storage objects according to the published retention policy.
8. Remove the direct `HARVEST_DIR` default from the customer-facing API. If an internal importer is temporarily necessary, run it as an authenticated one-off administrative ingestion job with an explicit tenant/project target and an audit record.
9. If URL import is offered, do not give the provider an arbitrary browser URL. Import it server-side with SSRF controls: HTTPS only; reject loopback, private, link-local, and cloud-metadata IP ranges after DNS resolution; cap redirects, bytes, and content type; scan/store an owned copy; then pass only the approved stored asset to the provider.

**Done when**

- No API response contains `D:\`, server filesystem roots, or a separate repository path.
- Enumerating assets never scans the filesystem recursively per customer request.
- A tenant B download attempt for tenant A's asset returns `404`.
- Deleting a project/asset follows a documented retention job and leaves no active delivery link.

### P0-05 — Add a durable worker, scheduler, and atomic claims

**Problem**

The new `tick` operation is a good bounded primitive but is not a production scheduler. Multiple workers can select the same pending job because selection and state transition are separate operations.

**Work-item table**

```sql
CREATE TABLE work_items (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  type TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','leased','running','retry_wait','succeeded','failed','cancelled','dead_letter')),
  priority INTEGER NOT NULL DEFAULT 100,
  run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  last_error JSONB,
  idempotency_key TEXT NOT NULL UNIQUE,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX work_items_claim_idx
  ON work_items (status, run_after, priority, created_at);
```

**Atomic claim query**

Use a transaction. Do not fetch candidate rows in Python first.

```sql
WITH candidates AS (
  SELECT id
  FROM work_items
  WHERE status IN ('pending', 'retry_wait')
    AND run_after <= now()
  ORDER BY priority ASC, created_at ASC
  FOR UPDATE SKIP LOCKED
  LIMIT :batch_size
)
UPDATE work_items w
SET status = 'leased',
    lease_owner = :worker_id,
    lease_expires_at = now() + interval '60 seconds',
    attempts = attempts + 1,
    updated_at = now()
FROM candidates
WHERE w.id = candidates.id
RETURNING w.*;
```

**Worker loop**

1. Start a process such as `python -m app.workers.film_worker`; do not start it inside the web app lifecycle.
2. Claim a small batch using the query above.
3. For each item, validate that the associated film version is still approved, grant is active, and cancellation has not been requested.
4. Execute one bounded action: plan, submit a render, poll a render, materialize media, assemble a segment, perform QC, or send notification.
5. Renew the lease for long operations. A second worker may reclaim only expired leases.
6. Write success/failure in the same transaction as related domain state changes where possible.
7. On a retryable failure, set `retry_wait` with backoff and structured error details. On terminal failure, set `dead_letter` and create a human-review task.
8. Run a separate reconciliation task every few minutes: find stale leases, renders submitted but not polled, missing storage objects, and provider jobs with unknown final states.

**Provider submission state machine**

Persist the provider idempotency key **before** calling the provider. A network timeout after submit is ambiguous: the provider might have accepted a charged job even though the client did not receive the response. Use this state flow:

```text
pending → leased → budget_reserved → submitting → queued_remote → running_remote
                                               ↘ reconciling_submission
queued_remote/running_remote → succeeded_remote → downloading → materialized → assembled
```

On timeout, move to `reconciling_submission`; do not put the job back into `pending` and blindly re-submit it. The reconciler must query the provider by the persisted idempotency key or provider request identifier. If the provider contract cannot support that lookup, add the capability before allowing live retries.

**Replace `/tick`**

Keep an internal/admin-only `POST /internal/films/{id}/advance-once` endpoint for debugging if needed. Remove public dependence on it. Customer APIs should only expose reads/events:

```http
GET /api/v2/projects/{project_id}/film-versions/{film_version_id}
GET /api/v2/projects/{project_id}/film-versions/{film_version_id}/events
```

**Done when**

- Closing the browser does not stop a film.
- Restarting an API or worker resumes safely without duplicate provider submission.
- Two worker processes never execute the same work item concurrently.
- Every in-flight job has a lease owner, expiry, and visible attempt history.

### P0-06 — Connect the real UI to persisted projects and films

**Problem**

The current page creates a project but then uses the literal `new-project` in pipeline URLs. It does not use the new `/films` route, and Export Film has no action.

**Implementation steps**

1. Create a project route: `/projects/[projectId]`. The URL, not a hidden component variable, is the source of the selected project ID.
2. After `POST /projects`, navigate to `/projects/{id}`. Store no fake fallback ID.
3. Split the current all-in-one `page.tsx` into feature modules:
   - `ProjectHeader`
   - `ScriptWorkspace`
   - `StoryBiblePanel`
   - `StoryboardAndAnimatic`
   - `ShotPlanReview`
   - `DailiesReview`
   - `TimelineEditor`
   - `SoundAndCaptions`
   - `DeliveryPanel`
4. Build a small typed API client; do not scatter hardcoded fetch URLs. Every call includes authenticated credentials and handles `401`, `403`, `404`, `409`, `422`, and `429` differently.
5. Replace the `handleRunPipeline` flow with a script/plan command that creates a new film version and waits for planning status through events/polling.
6. Render a mandatory `PlanApprovalDialog` showing: logical shots, unique renders, duration, quality preset, current capacity/ETA range, known budget or policy allowance, and required approval text.
7. The only button that creates render work is labelled `Approve plan and start render`; it should call the new authenticated render command once. Disable it after click until an idempotent response arrives.
8. Implement Export Film only when final QC has passed. It should issue a protected delivery request rather than link to a raw local file.
9. Delete fabricated ready states and fabricated video URLs. UI status must derive only from persisted API status.
10. Either repair `Canvas.tsx` and wire it to real asset/timeline APIs, or keep it out of the route tree until it is valid. Never ship a visually impressive but fake generation control.

**Done when**

- Every visible project, scene, shot, clip, and final film has a persisted ID from the API.
- Reloading the page shows the same server state without simulated completion.
- The UI can render a project only if the signed-in tenant owns it.
- Export creates an authorized delivery action, not a dead button.

### P0-07 — Isolate mock mode

**Implementation steps**

1. Make mock backend selection available only when `APP_ENV in {development, test}` or when the caller has an internal operator role.
2. Mark all mock artifacts with `is_synthetic=true`, `environment`, `watermark_required=true`, and a visible `TEST OUTPUT — NOT CUSTOMER FOOTAGE` slate/watermark.
3. Make the public production API reject client supplied `backend="mock"` and `backend="live"`. Use server policy as described in ADR-05.
4. Separate development mock storage from production customer storage.
5. Add a production startup check that fails if mock delivery routes are exposed outside development/test.

**Done when**

- A normal customer cannot produce or download a mock artifact from the production tenant flow.
- Any internal mock media is visibly and programmatically marked synthetic.

### P0-08 — Fix deduplication and idempotency correctly

**Problem**

The current planner increments the seed for every shot, while deduplication requires equal seed. Additionally, Jaccard-style near-text matching is unsafe for cinema: two prompts can share words while depicting different action, geography, or continuity.

**Correct design**

Use three distinct identifiers. Do not overload one hash for all purposes.

| Identifier | Scope | Inputs | Use |
| --- | --- | --- | --- |
| `client_request_id` | Tenant + command | Random UUID generated by client once per button click | Network-command idempotency. |
| `plan_fingerprint` | Film version | Locked screenplay version, bible version, planning model/version, settings | Detect/reuse an identical approved plan if policy permits. |
| `render_fingerprint` | Tenant + output spec | Exact normalized prompt, negative prompt, model/version, duration, aspect ratio, seed, reference **asset hashes**, settings | Exact render reuse only. |

**Rules**

1. Do not deduplicate by fuzzy/Jaccard similarity in the first production release.
2. Deduplicate only when every render-affecting field is exactly identical after normalization.
3. A repeated clip must be intentional. Store `reuse_of_shot_id` or let the planner emit `reuse_existing_render: true`; surface it in the shot-plan review screen.
4. If repeat footage should be identical, assign the same deterministic render seed derived from the same render fingerprint. If it should be visually similar but not identical, use a new seed and render a new variant.
5. Scope render reuse to the same tenant by default. Cross-tenant asset reuse must be disabled unless a future licensed stock-library product explicitly supports it.
6. Store cost allocation in a separate table; never double-count a globally shared job merely because two shots reference it.

**Recommended tables**

| Table | Key fields |
| --- | --- |
| `render_specs` | `id`, `tenant_id`, `render_fingerprint`, all exact render inputs, `UNIQUE(tenant_id, render_fingerprint)` |
| `render_jobs` | `id`, `render_spec_id`, `execution_policy_id`, `status`, provider IDs, attempts, output asset ID |
| `shot_render_usages` | `shot_id`, `render_job_id`, `usage_kind` (`primary`, `reuse`, `variant`) |
| `render_cost_allocations` | `render_job_id`, `film_version_id`, `tenant_id`, `amount`, `allocation_reason` |

**Regression tests**

- Same prompt but different seed → two render specs/jobs.
- Same exact spec with `reuse_existing_render=true` → one render job, two shot usages.
- Similar wording but different action/continuity → two render jobs.
- Same exact prompt/spec from two tenants → two tenant-isolated render specs/jobs.
- A cost from one render job is allocated once according to the chosen policy and is never accidentally billed twice.

### P0-09 — Bind execution policy to the film, not HTTP input

**Implementation steps**

1. Add `execution_policies` with `id`, `name`, `environment`, `quality_preset`, `provider_contract_version`, `max_duration_seconds`, `max_concurrent_renders`, `budget_policy`, and `enabled`.
2. When a film version is created, the server chooses and persists `execution_policy_id` based on tenant grant and environment.
3. Persist the provider contract version and all approved render settings on the render specification.
4. Workers load the persisted policy. They do not accept `backend`, `live`, or `max_clips` from a customer API request.
5. Restrict operational overrides to a separately authenticated admin endpoint that writes an audit record and requires a reason.
6. On plan approval, snapshot policy and entitlement terms so a later configuration change cannot silently alter an already approved budget/quality promise.

### P0-10 — Make production configuration fail closed

**Problem**

Development-friendly defaults are dangerous in a paid product. A process must not quietly start against a local SQLite file, a default signing secret, local public storage, debug mode, or a mock/live ambiguity.

**Implementation steps**

1. Add `APP_ENV` with only `development`, `test`, `staging`, and `production` allowed.
2. In settings validation, when `APP_ENV` is `staging` or `production`, reject startup unless all of the following are true:
   - `DATABASE_URL` is PostgreSQL, not SQLite;
   - the application/session secret is non-default, high entropy, and at least 32 bytes/characters as appropriate;
   - private object storage configuration exists;
   - the payment webhook verification secret exists;
   - debug mode is disabled;
   - legacy demo routes are disabled;
   - mock execution policy is disabled for customer tenants;
   - live rendering has an explicit server-side emergency kill switch.
3. Add `LIVE_RENDERING_ENABLED=false` as the safest production default. When false, the worker pauses new submissions with a visible `paused_by_operator` status; it never falls back to mock generation.
4. Use database migrations (`alembic upgrade head`) in deployment. Do not rely on `Base.metadata.create_all()` in production.
5. Add a startup test matrix covering valid development/test configuration and invalid production configurations.

**Done when**

- A misconfigured production deployment fails before accepting requests.
- A provider outage/financial incident can stop new spend without losing the ability to poll/reconcile existing jobs.

---

## 5. P1 studio workflow implementation plan

The goal is not merely to produce clips. It is to give the customer a dependable, reviewable production process comparable to a compact studio.

### 5.1 Production phases, roles, artifacts, and gates

| Phase | Studio responsibility | Required product artifact | Mandatory gate before next phase |
| --- | --- | --- | --- |
| Development | Producer, writer, showrunner | logline, format, audience, rights declarations, treatment | Greenlight / project setup |
| Writing | Writer, script coordinator | screenplay versions, scene numbers, dialogue/narration, locked script | Script lock |
| Visual development | Director, art director, production designer | show bible, character sheets, locations, style references | Look approval |
| Preproduction | Storyboard artist, editor, script supervisor, production manager | scene breakdown, boards, animatic, continuity ledger, render estimate | Plan approval |
| Production | AI technical director, render manager | ordered shots, render variants, dailies, provider provenance | Dailies approval / exceptions |
| Editorial | Picture editor | versioned timeline/EDL, trims, transitions, selected takes | Picture lock |
| Sound/post | sound editor, composer, mixer, colorist | dialogue/narration, music, Foley, subtitles, color/QC reports | Final QC pass |
| Delivery | finishing producer, customer success | master, streaming/download package, thumbnail, credits, delivery audit | Customer delivery |

#### 5.1.1 Crew responsibility map

The application does not need a separate AI agent or human login for every title on day one. It does need a durable responsibility, artifact, approver, and audit trail for each title below. Otherwise the workflow collapses into unreviewable prompt generation.

| Studio role | Product responsibility | Durable output / control |
| --- | --- | --- |
| Executive Producer / customer | Owns intent, commercial use, budget approval, and final sign-off. | Project brief, policy/rights attestation, approval decisions. |
| Development Producer | Makes the premise feasible for target audience, format, duration, and policy. | Logline, treatment, feasibility/risk notes. |
| Screenwriter / script coordinator | Maintains scene numbers, dialogue, continuity of story revisions. | Versioned screenplay and locked script. |
| Director / showrunner | Preserves dramatic and visual intent across sequences and cuts. | Director intent, sequence notes, dailies/cut approvals. |
| Art Director / Production Designer | Defines palette, locations, props, wardrobe, lighting, and visual grammar. | Approved look/style package and reference assets. |
| Character / Casting / Voice Director | Defines performance identity and confirms likeness/voice rights. | Character/voice profiles, consent and usage records. |
| Storyboard Artist / Previs Editor | Turns script into boards, timing, camera grammar, and animatic. | Storyboards, shot cards, animatic revision. |
| 1st AD / Production Manager | Makes the plan operationally and financially feasible. | Capacity snapshot, cost/ETA range, render authorization. |
| Script Supervisor / Continuity Lead | Prevents visual/story state inconsistencies. | Continuity ledger, scene transition checks, change-impact report. |
| AI/VFX Production Supervisor | Manages render execution, provider failure, dailies, and provenance. | Render jobs, attempt lineage, variant/dailies status. |
| Picture Editor | Turns selected takes into a coherent cut. | Timeline revisions, EDL manifest, picture lock. |
| Sound Supervisor / Composer / Mixer | Builds dialogue, music, ambience, Foley, captions, and mix. | Audio cues, stems, mix revision, sound lock. |
| Colorist / Online Finisher | Conforms approved footage and produces a consistent master. | Grade/online revision, title/credit package, master manifest. |
| QC / Delivery Producer | Verifies technical/content readiness and publishes outputs. | QC reports/issues, delivery clearance, master package. |
| Rights / Compliance Reviewer | Handles flagged source, likeness, music, and output-policy issues. | Rights status and documented review decision. |
| Customer Success / Support | Restores access and safely handles operational issues. | Audited support case, account/grant recovery actions. |

### 5.2 Implement versioned creative artifacts first

Create these domain objects before attempting feature-scale rendering:

```text
Project
  ├─ ScriptVersion (draft → in_review → locked)
  ├─ ShowBibleVersion (draft → approved)
  ├─ StoryboardVersion / AnimaticVersion (draft → approved)
  ├─ FilmVersion
  │   ├─ Sequence
  │   │   ├─ Scene
  │   │   │   ├─ Shot
  │   │   │   │   ├─ RenderVariant / DailiesAsset
  │   │   │   │   └─ ContinuityNotes
  │   └─ TimelineVersion (draft → picture_locked)
  └─ MasterVersion (qc_pending → approved → delivered)
```

Every approved object is immutable. Editing creates a new version or revision. Do not mutate a locked screenplay in place and then keep rendering against an unrecorded change.

**Revision and stale-state algorithm**

1. Every creative edit creates `revision_number + 1` with `parent_revision_id`, `content_hash`, author, and timestamp.
2. An approval stores the exact revision ID **and** content hash. Never approve a mutable logical object without a revision.
3. On an upstream change, find all derived objects using stored source-revision links. Mark them `stale`; do not delete their historic output.
4. A stale storyboard, animatic, shot plan, render authorization, timeline, sound mix, QC report, or master cannot advance to its next gate until it is regenerated/re-reviewed or an authorized reviewer explicitly accepts the impact.
5. A change to a locked script produces a new script revision and a `ChangeRequest`/impact report: affected scenes, shots, rendered clips, timeline items, captions, and sound cues.
6. A picture change after picture lock creates a new timeline revision and automatically marks sound, finishing, QC, and delivery artifacts stale.
7. Preserve all prior approved revisions for audit, comparison, rollback, and customer history. "Current" is a pointer, not destructive replacement.

### 5.3 Script, scene, and shot planning

**Required scene fields**

```json
{
  "scene_number": "12",
  "sequence_number": 3,
  "slugline": "INT. ARCHIVE — NIGHT",
  "story_time": "night_3",
  "dramatic_goal": "The protagonist learns the betrayal.",
  "characters_present": ["character-id"],
  "locations": ["location-id"],
  "props_required": ["prop-id"],
  "wardrobe_state": {"character-id": "coat-rain-wet"},
  "continuity_in": {},
  "continuity_out": {},
  "approved_duration_ms": 42000
}
```

**Required shot fields**

```json
{
  "shot_number": "12B",
  "shot_order": 2,
  "purpose": "Reveal the hidden letter.",
  "camera": {"framing": "close_up", "movement": "slow_push_in", "lens": "50mm"},
  "screen_direction": "left_to_right",
  "action": "Maya unfolds the letter and stops breathing.",
  "dialogue_or_audio_cue": "...",
  "duration_ms": 4500,
  "continuity_requirements": {},
  "render_strategy": "new_render",
  "reuse_of_shot_id": null,
  "approval_status": "draft"
}
```

**Planner implementation rules**

1. Plan in hierarchy: act → sequence → scene → shot. Do not ask an LLM to independently invent 2,160 five-second prompts with only a static global bible.
2. Generate a structured plan for one sequence at a time. Feed forward the approved prior sequence summary and explicit continuity state, not the raw entire script on every request.
3. Validate LLM output with a JSON schema. On malformed output, run a bounded repair pass; on repeated failure, create a planning-review task rather than fail the entire film silently.
4. Keep prompt construction deterministic and recorded: template version, planner model version, inputs, output, and timestamp.
5. Give a human/customer an approval view before render submission. Show every reuse, repeat, expected duration, and risk/continuity warning.

### 5.4 Continuity ledger

Create `continuity_entities` and `continuity_states` rather than keeping continuity solely inside free-form JSON prompts.

| Entity type | Examples | Fields to track |
| --- | --- | --- |
| Character | Maya, antagonist | look/reference assets, age, hairstyle, wardrobe, emotional state, injuries, voice, screen direction |
| Location | archive, rooftop | time of day, weather, lighting, damage state, set dressing |
| Prop | letter, key, car | owner, condition, current location, held-by, appearance state |
| Story state | mystery solved? | facts known, relationships, temporal state, unresolved beats |

At each shot transition, compare `continuity_out` of the prior shot to `continuity_in` of the next. Flag inconsistent values for review. A rule engine can start simply: mismatched wardrobe, a prop held by two people, location/time mismatch, impossible character presence, and reversed screen direction without a cutaway/transition.

### 5.5 Dailies, variants, and human review

For every completed render, retain:

- exact render spec and policy snapshot;
- provider request/job identifiers;
- input asset hashes;
- preview asset and normalized production asset;
- technical QC result;
- automated visual/continuity flags;
- reviewer decision: `select`, `request_variant`, `reject`, `needs_human_review`;
- reviewer comment and timestamp.

Do not overwrite a bad take. Create `RenderVariant` records. An editor selects the variant used by the timeline.

### 5.6 Editorial timeline

The current hard concat is a useful assembly primitive, but it is not an editing system. Add these records:

| Table | Key fields |
| --- | --- |
| `timeline_versions` | `id`, `film_version_id`, `version_number`, `status`, `duration_ms`, `created_by` |
| `timeline_tracks` | `id`, `timeline_version_id`, `kind` (`video`, `dialogue`, `music`, `sfx`, `captions`) |
| `timeline_items` | `id`, `track_id`, `asset_id/render_variant_id`, `start_ms`, `in_ms`, `out_ms`, `gain_db`, `transition_json`, `order` |
| `editorial_decisions` | `id`, `timeline_version_id`, `shot_id`, `decision`, `reason`, reviewer |

Start with simple, safe editorial controls:

1. choose a rendered variant for each shot;
2. reorder shots only within approved scene rules;
3. trim in/out points;
4. hard cut / dissolve / fade transitions;
5. mute/replace clip audio;
6. export an immutable EDL-like JSON manifest;
7. assemble only an approved `picture_locked` timeline.

Do not allow arbitrary client-side rendering. Save an editorial command, validate it, then have a worker assemble it.

### 5.7 Sound, captions, finishing, and QC

**Sound deliverables**

- narration/dialogue tracks with speaker, script version, pronunciation, voice consent/source, and loudness metadata;
- music cue sheet with source/license/usage terms;
- ambience/Foley/SFX tracks;
- mix version with target loudness and peak rules;
- audio QC report: missing dialogue, clipping, silence, duration mismatch.

**Finishing deliverables**

- title card/credits version;
- color/look consistency report;
- captions/subtitles in at least WebVTT and SRT;
- localization version metadata;
- technical master report: codec, resolution, aspect ratio, duration, frame rate, audio streams, checksum;
- thumbnail/trailer/preview derivatives;
- content/QC review status.

**Minimum QC checks before delivery**

1. all selected timeline assets exist and have matching tenant ownership;
2. no failed, quarantined, or unapproved shot variant is in the edit;
3. final duration is within tolerance of the approved timeline;
4. no black/frozen/missing-video section exceeds a defined threshold;
5. audio exists when the project promises audio;
6. caption timing and language match the version;
7. final object checksum, playback probe, codec/resolution, and subtitle manifest are recorded;
8. customer-visible credits/rights warnings have been reviewed.

---

## 6. Detailed film-pipeline repairs

### 6.1 Replace the current content-keyed film idempotency with command idempotency

The current request fingerprint makes a `refused_capacity` record sticky across a later request that chooses a different admission strategy. A content match is not the same thing as a retry of the same business command.

**Implement this instead:**

1. Require an `Idempotency-Key` HTTP header on every create/approve/render command. It must be a UUID generated once per UI click.
2. Store `tenant_id`, endpoint/action, request body hash, response status/body, and `idempotency_key` in `idempotency_records` with `UNIQUE(tenant_id, endpoint, idempotency_key)`.
3. If the same key and same body repeat, return the original response. If the same key has a different body, return `409 Conflict`.
4. If the customer wants to re-plan after a capacity refusal, create a new command/key and a new film-version plan revision. Preserve the refused attempt in history.
5. Use `plan_fingerprint` only for optional plan caching/reuse, never as the sole primary business identity.

### 6.2 Preserve job lineage and make re-routing possible

The frozen contract may return provider data but not a complete seat/reassignment mechanism. The product must preserve what happened and avoid unsafe blind reposts.

**Tables**

| Table | Important fields |
| --- | --- |
| `render_attempts` | `id`, `render_job_id`, `attempt_number`, `provider`, `provider_job_id`, `provider_seat nullable`, `status`, `requested_at`, `completed_at`, `error_class`, `error_detail`, `credits_reserved`, `credits_spent` |
| `provider_health_events` | `id`, `provider`, `seat`, `kind`, `detected_at`, `retry_after`, `detail` |
| `review_tasks` | `id`, `tenant_id`, `resource_type`, `resource_id`, `reason_code`, `priority`, `status`, `assigned_to` |

**Rules**

- A render job has many attempts but only one active attempt at a time.
- A terminal `wall:` or `auth:` result marks the relevant seat/provider unhealthy and creates an operator task if no eligible alternative exists.
- A retry on another provider/seat creates a new `render_attempt` with an explicit lineage reference. It does not overwrite the original provider job ID.
- The policy decides whether a retry retains the same visual seed, changes a seed, or requests customer approval. Record that decision.
- Never use a generic retry loop that submits a potentially charged job repeatedly without a durable idempotency/attempt check.

### 6.3 Make capacity and ETA customer-honest

At plan approval, calculate and persist a `render_admission` record:

```json
{
  "required_new_renders": 312,
  "approved_reuses": 18,
  "duration_seconds": 1800,
  "capacity_snapshot": {"observed_at": "...", "available": 40},
  "policy_snapshot": {"max_concurrency": 5, "quality_preset": "standard"},
  "estimated_start_window": "...",
  "estimated_completion_range": {"min": "...", "max": "..."},
  "cost_policy": {"customer_charge": 0, "fair_use_units": 312},
  "status": "approved"
}
```

Show the result as an estimate, not a promise. Provider availability and rate limits change. If capacity falls below the admission assumptions, park the film visibly and notify the customer; do not pretend it is rendering.

### 6.4 Add cancellation and safe stop points

Implement:

```http
POST /api/v2/projects/{project_id}/film-versions/{film_version_id}/cancel
POST /api/v2/projects/{project_id}/film-versions/{film_version_id}/resume
```

Cancellation must:

1. set the film version to `cancellation_requested`;
2. prevent new render submission immediately;
3. attempt provider cancellation only for work that has not completed;
4. preserve completed assets/dailies for the customer according to policy;
5. reconcile any pending/reserved provider spend;
6. create an audit event and notify the customer.

Do not delete completed assets as a side effect of cancellation.

### 6.5 Use longer clips only with a validated shot strategy

The current fixed five-second assumption is acceptable for a prototype. Do not merely expose a longer duration knob. First add shot classifications:

| Shot class | Typical duration | Rule |
| --- | --- | --- |
| Establishing / static | 6–12 seconds | Eligible for longer source clip if provider supports it. |
| Dialogue reaction | 3–6 seconds | Short, continuity-sensitive. |
| Action / montage | 2–5 seconds | Prefer short clips and editorial rhythm. |
| Reusable insert | 3–8 seconds | Exact reuse allowed only with explicit planner flag. |

Validate provider duration/cost semantics in staging before using longer clips in production. Store actual source duration and trim safely in the timeline; never assume the returned duration matches the request.

---

## 7. Public API contract

All public paths below require authentication. All resource queries are tenant-scoped. The response shape should include stable IDs, status, timestamps, and an event cursor where applicable.

### 7.1 Project and creative APIs

```http
POST   /api/v2/projects
GET    /api/v2/projects
GET    /api/v2/projects/{project_id}
PATCH  /api/v2/projects/{project_id}

POST   /api/v2/projects/{project_id}/scripts
GET    /api/v2/projects/{project_id}/scripts
POST   /api/v2/projects/{project_id}/scripts/{script_id}/lock

POST   /api/v2/projects/{project_id}/show-bibles
POST   /api/v2/projects/{project_id}/storyboards
POST   /api/v2/projects/{project_id}/film-versions
POST   /api/v2/projects/{project_id}/film-versions/{film_version_id}/plan
POST   /api/v2/projects/{project_id}/film-versions/{film_version_id}/approve-plan
POST   /api/v2/projects/{project_id}/film-versions/{film_version_id}/render
POST   /api/v2/projects/{project_id}/film-versions/{film_version_id}/cancel
GET    /api/v2/projects/{project_id}/film-versions/{film_version_id}
GET    /api/v2/projects/{project_id}/film-versions/{film_version_id}/events
```

### 7.2 Dailies/editorial/post APIs

```http
GET    /api/v2/projects/{project_id}/film-versions/{film_version_id}/shots
POST   /api/v2/projects/{project_id}/film-versions/{film_version_id}/shots/{shot_id}/variants
POST   /api/v2/projects/{project_id}/film-versions/{film_version_id}/shots/{shot_id}/select-variant

POST   /api/v2/projects/{project_id}/film-versions/{film_version_id}/timeline-versions
PATCH  /api/v2/projects/{project_id}/timeline-versions/{timeline_id}
POST   /api/v2/projects/{project_id}/timeline-versions/{timeline_id}/picture-lock

POST   /api/v2/projects/{project_id}/timeline-versions/{timeline_id}/audio-versions
POST   /api/v2/projects/{project_id}/timeline-versions/{timeline_id}/qc
POST   /api/v2/projects/{project_id}/timeline-versions/{timeline_id}/master
GET    /api/v2/projects/{project_id}/masters/{master_id}/delivery
```

### 7.3 Command response pattern

Every asynchronous command should respond quickly:

```json
{
  "command_id": "cmd_...",
  "resource_id": "filmver_...",
  "status": "queued",
  "event_cursor": "evt_...",
  "idempotent_replay": false
}
```

Use `202 Accepted` for a queued command, `201 Created` for a created synchronous record, `409 Conflict` for stale revision/idempotency mismatch, `422 Unprocessable Entity` for a missing prerequisite (for example an unlocked script), and `429 Too Many Requests` only for enforceable rate/concurrency limits.

### 7.4 Server-sent events / polling

Start with polling if SSE delivery complexity would delay security work. The status response must support a monotonic `version` or `updated_at` and event cursor. Then add SSE:

```text
event: film.status
id: evt_01...
data: {"film_version_id":"...","from":"rendering","to":"waiting_capacity","reason":"..."}
```

Persist events before publishing. On reconnect, `Last-Event-ID` must replay missed events from `project_activity`/`film_events`.

---

## 8. UI implementation guide

### 8.1 Required route flow

```text
/sign-in
  → /library
  → /projects/new
  → /projects/{projectId}/development
  → /projects/{projectId}/script
  → /projects/{projectId}/look
  → /projects/{projectId}/plan
  → /projects/{projectId}/dailies
  → /projects/{projectId}/edit
  → /projects/{projectId}/sound
  → /projects/{projectId}/delivery
```

The route itself identifies the active project. Do not use a hardcoded `new-project`, implicit global state, or a fabricated default project.

### 8.2 UI state rules

1. Treat server data as authoritative. Local optimistic state must roll back on an API failure.
2. Never set a render to `ready` until the API reports a ready asset with an owned asset ID.
3. Display immutable state transitions: `draft`, `awaiting_approval`, `queued`, `planning`, `waiting_capacity`, `rendering`, `review_required`, `editing`, `qc_pending`, `completed`, `failed`, `cancelled`.
4. Show useful failure language: what failed, whether money was spent/reserved, whether customer action is needed, and a safe next action.
5. Any spend-affecting action has a confirmation dialog summarizing approved plan/capacity/fair-use impact. It must not expose raw provider secrets or internal seat data.
6. Error boundaries must catch malformed/unavailable optional modules. A canvas compile failure must never take down the project screen.

### 8.3 First build slices for a junior engineer

Implement in this exact order:

1. Authenticated `ProjectList` and `CreateProject` page using real IDs.
2. `ProjectShell` that fetches `/projects/{id}` and handles `404`/loading/error.
3. `ScriptWorkspace` with version history and `Lock script` action.
4. `FilmVersionCreate` and read-only plan status page.
5. `PlanApprovalDialog` and render command.
6. `FilmProgressPanel` polling the API every 5–10 seconds, later upgraded to SSE.
7. `DailiesReview` with select/reject/request-variant controls.
8. Minimal timeline editor.
9. QC/delivery page with protected download.

Do not start by rebuilding a drag-and-drop canvas. A reliable, typed workflow produces a usable studio sooner and prevents fake visual progress.

---

## 9. Security, rights, privacy, and safety requirements

### 9.1 Security baseline

- Use HTTPS in every non-local environment.
- Keep provider keys in a secret manager/environment, never in client code or logs.
- Redact tokens, payment data, raw access-link tokens, and provider credentials in logs.
- Rate limit authentication, upload creation, planning commands, render approval, and delivery link generation by tenant/user/IP as appropriate.
- Require CSRF protection for cookie-based sessions; use secure, `HttpOnly`, `SameSite` cookies where applicable.
- Validate all uploaded file types by content sniffing and size, not just filename extension.
- Scan uploads and provider downloads before they become ready customer assets.
- Store checksums and provenance for inputs and masters.
- Maintain audit events for administrative overrides, entitlement changes, policy changes, render submissions, asset access, and delivery links.

### 9.2 Rights and consent fields

Before accepting reference images, voices, music, scripts, or logos, collect and persist declarations:

- uploader asserts they own or have permission to use the reference;
- voice/likeness consent and allowed usage scope;
- music license/source and territory/platform restrictions;
- prohibited content and policy acknowledgement;
- retention/deletion request handling;
- whether generated output may be reused internally for improvement (default should be opt-out/disabled until legal policy is defined).

Do not claim legal clearance merely because a checkbox exists. The feature should preserve declarations and flag high-risk work for review.

### 9.3 Lifetime access is not indefinite free infrastructure

Document a fair-use policy in the grant's `policy_json`. A practical product policy can provide lifetime account access while limiting abusive behavior through:

- maximum concurrent films;
- maximum active render jobs;
- maximum upload size/storage retained;
- project/archive retention tiers;
- per-day/per-month compute allocation or queue priority;
- no resale/automated bulk generation;
- manual review for exceptional load;
- provider outage and force-majeure wording.

The exact commercial policy is a product/legal decision. The engineering requirement is that it is machine-enforced, auditable, understandable in the UI, and snapshot at approval time.

### 9.4 Rights, consent, provenance, and privacy workflows

This section is an engineering baseline, not a substitute for legal counsel. Counsel must approve the customer-facing terms, privacy notice, acceptable-use policy, likeness/voice consent language, retention schedule, refund policy, and any required synthetic-media disclosure before public launch.

**Persist separate records; do not hide them in one generic project JSON field.**

| Record | Minimum engineering purpose |
| --- | --- |
| `policy_documents` / `policy_acceptances` | Versioned product/fair-use/privacy/acceptable-use terms and who accepted which version. |
| `source_assets` / `rights_attestations` | Origin, uploader, license/ownership assertion, commercial use scope, restrictions, expiry. |
| `consent_records` | Likeness/voice subject, scope, evidence asset, validity, verifier, revocation status. |
| `asset_lineage` | Parent/child relationship, provider/model/version, prompt/settings hash, input asset versions. |
| `moderation_cases` | Policy result, review/appeal state, decisions, public-safe reason code. |
| `provider_processing_events` | When sensitive customer inputs were sent to which provider and any deletion request/result. |
| `privacy_requests` | Verified export/deletion request, state, action log, legal-hold exception, completion. |

**Source-media gate before planning/rendering**

1. Record whether the asset is customer-created, customer-uploaded, licensed stock, client-supplied, or provider-generated.
2. Require an ownership/usage attestation and intended-use scope.
3. Ask whether it contains an identifiable person, recognizable voice, minor, copyright-sensitive character/logo, or confidential client material.
4. For a recognizable face or voice, require an active scoped consent/release before provider submission. Treat minor-related media as a special policy/human-review case rather than an ordinary upload.
5. Store a separate opt-in/opt-out for training or product improvement; default the product pipeline to no persistent training/fine-tuning on customer uploads unless there is informed, separate authorization.
6. On consent revocation or valid rights/takedown event, block future use, cancel/hold queued work when safe, revoke affected public/share links, put downstream derivatives into review, and preserve only restricted records required for accounting/fraud/legal obligations.

**Provenance manifest for every final delivery**

Generate an owned, access-controlled JSON manifest containing at least:

```json
{
  "delivery_version": "v3",
  "project_id": "...",
  "created_at": "UTC timestamp",
  "asset_checksums": [],
  "source_asset_lineage": [],
  "approved_revision_ids": [],
  "human_review_events": [],
  "generation_provider_records": [],
  "model_identifiers": [],
  "prompt_and_settings_hashes": [],
  "rights_attestation_ids": [],
  "consent_record_ids": [],
  "synthetic_media_disclosure": true,
  "usage_notice_version": "..."
}
```

Do not include raw consent documents, unredacted internal prompts, provider credentials, moderation notes, access tokens, or unnecessary personal information in a broadly shareable delivery manifest.

**Privacy endpoints and behavior**

```http
POST /api/v2/privacy/export-requests
GET  /api/v2/privacy/export-requests/{request_id}
POST /api/v2/privacy/deletion-requests
GET  /api/v2/privacy/deletion-requests/{request_id}
POST /api/v2/consents/{consent_id}/revoke
```

For an approved deletion request: verify identity; revoke sessions and share links; make media inaccessible; cancel pending work where safe; create object/provider deletion jobs; preserve only legally required restricted records; and write a deletion tombstone so delayed webhooks/jobs cannot silently recreate deleted content. Test backup retention/deletion propagation and document the residual backup-retention period honestly.

### 9.5 Private delivery, review, sharing, and customer support

**Delivery package**

Never overwrite an approved final delivery. A rework creates a new immutable `delivery_version`. A QC-cleared package may contain:

- final MP4 in the promised resolution/aspect ratio;
- preview, poster, and thumbnail;
- captions/subtitles (`.srt`/`.vtt`) when included;
- approved audio stems/source archive only when promised and permitted;
- checksum/provenance manifest;
- customer-readable usage/license notice and hosted-retention information.

**Share-link model**

Create `share_links` with `delivery_package_id`, `token_hash`, `permission` (`view`, `comment`, `download`), `expires_at`, optional `password_hash`, optional `max_uses`, `revoked_at`, creator, and audit timestamps.

Rules:

1. A share link is distinct from the customer’s account/lifetime grant.
2. Validate the secret, scope, expiry, password/use-limit, and delivery/rights status before issuing a short-lived object URL.
3. Revoke it immediately after deletion, takedown, consent withdrawal, entitlement suspension, or manual revocation.
4. Record a media-access audit event with only privacy-appropriate request information (for example a hashed IP prefix, not raw secret URLs).
5. Support browser video range requests through an authorized signed URL/CDN policy. Do not make a whole storage bucket public merely to play video.

**Support and refund model**

Implement `support_cases`, `support_messages`, `support_access_grants`, `refund_requests`, and `service_incidents`.

- Give customers a “Get help” action on billing, project, render, delivery, rights, and privacy screens.
- Attach safe diagnostics automatically: correlation ID, project/job ID, public failure code, client version, and state. Do not attach raw prompts/media/payment information by default.
- Support staff have **no standing access** to customer media. Access requires a customer-approved, project-scoped, time-limited support grant and creates an audit event.
- Any refund, usage-credit, entitlement override, or provider-cost adjustment must reference a support case and create immutable ledger/audit records.
- Maintain incident procedures for private-media exposure, account takeover, non-consensual likeness/voice complaint, provider-wide outage, and failed final delivery.

---

## 10. Test, CI, and release plan

### 10.1 Test pyramid

| Layer | Required tests |
| --- | --- |
| Unit | authorization predicates, policy evaluator, render fingerprint, idempotency record, backoff, continuity rules, cost allocator |
| Repository/database | tenant-scoped queries, row-lock claims, lease expiry, migrations, no phantom project reads/writes |
| API integration | auth required, cross-tenant 404, payment-webhook idempotency, plan approval prerequisites, safe cancellation, delivery authorization |
| Worker integration | restart recovery, two-worker race, provider transient/wall/auth/capacity scenarios, no duplicate submit, output materialization |
| Media integration | upload validation, checksum, duration, ffmpeg probe, assembly, audio/caption mux, QC failure cases |
| Frontend | authenticated route flow, no fake ready state, error/retry UX, plan-confirmation, protected delivery |
| End-to-end staging | purchase/grant → project → script lock → plan approval → controlled small real render → review → edit → QC → protected delivery |

### 10.2 Specific regression tests for existing findings

1. A production-configured legacy animation endpoint returns `410` and submits no provider job.
2. An unauthenticated `/films`/project/assets request returns `401`.
3. Tenant B cannot read tenant A's project, asset, final film, delivery URL, or event stream.
4. Unknown project read/update returns `404`; it never creates a default/phantom record.
5. Replaying a payment webhook creates exactly one order and grant.
6. Replaying a render command with the same idempotency key returns the original command response and no new work item.
7. Retrying with a new command ID after a capacity refusal can create a new plan/admission attempt.
8. Two workers claiming the same queue concurrently submit one render attempt only.
9. A mock artifact cannot be delivered through the production customer API.
10. Exact intentional render reuse creates one job/two usages; fuzzy similar prompts do not reuse.
11. UI tests confirm no literal `new-project`, fake `ready` video URL, or dead Export action remains.
12. The repaired canvas parses/type-checks, or it is not imported by production routes.
13. Production startup fails with a default/weak secret, SQLite database URL, debug enabled, missing private storage, missing payment webhook verification secret, or mock profile enabled for customer traffic.
14. A worker timeout during provider submission enters reconciliation and does not issue a second provider submission until the persisted idempotency key has been reconciled.

### 10.2.1 Customer-trust regression cases

| ID | Scenario | Expected result |
| --- | --- | --- |
| BILL-01 | Browser reaches payment-success page without a verified webhook. | No active grant is created. |
| BILL-02 | The same valid payment webhook is delivered twice. | Exactly one order, grant, and activation audit event exist. |
| BILL-03 | Refund/chargeback is received after activation. | Grant state updates according to policy; all state changes are audited. |
| RIGHTS-01 | A recognizable face/voice is used without active consent. | Provider submission is blocked with a safe public reason. |
| RIGHTS-02 | Consent is revoked while work is queued. | Future use/sharing is blocked, queued work is safely held/cancelled, and audit evidence exists. |
| PRIV-01 | Customer requests data export. | A time-limited export includes only authorized data. |
| PRIV-02 | Customer requests deletion. | Sessions/share links are revoked, media becomes inaccessible, deletion jobs/tombstone are recorded, and delayed jobs cannot recreate it. |
| MEDIA-01 | Caller attempts an internal filesystem path, object key, or harvest filename. | It is not routable/servable in production. |
| MEDIA-02 | Signed delivery URL/share link is expired or revoked. | Access fails without metadata leakage. |
| MEDIA-03 | A delivery package becomes ready. | All listed assets exist, pass media probe/checksum, and have a manifest entry. |
| SUPPORT-01 | Support agent opens customer media without a current grant. | Access is denied and an audit event is recorded. |
| OBS-01 | Mock paid flow runs from grant through delivery. | A correlation ID links entitlement, approval, reservation, jobs, provider records, output, and delivery access. |

### 10.3 CI gates

Every pull request must run:

```text
backend unit + integration tests
database migration up/down validation on disposable database
worker race/recovery tests
frontend lint + typecheck + component tests
OpenAPI contract checks
secret scan
dependency/security scan
documentation link/markdown check
```

Fix the current frontend Jest TypeScript setup before claiming frontend coverage. Do not mark CI green by simply excluding the malformed canvas or existing failing model test; either fix, quarantine with an owner/ticket, or explicitly classify it as legacy code not deployed.

### 10.4 Staged rollout

| Stage | Scope | Required evidence |
| --- | --- | --- |
| 0 — local | Mock-only, no customer data | Unit/integration green, no live credentials needed |
| 1 — staging | Internal accounts, synthetic/test assets | Worker recovery, tenant isolation, manual provider smoke test with explicit tiny cap |
| 2 — private alpha | Small invited customers, strict fair-use | Audited payments/grants, monitored jobs, support runbook, rollback exercised |
| 3 — beta | Limited paid cohort | QC/delivery, cost reconciliation, queue/ETA accuracy, incident response |
| 4 — public | General availability | P0/P1 complete, security review, legal/policy approval, capacity and support readiness |

Do not make the lifetime/unlimited claim at Stage 1. Verify the economic and operational model with real, measured cohorts first.

---

## 11. Migration and operational runbook

### 11.1 Safe migration order

1. Back up the existing databases and storage metadata; record a checksum and restore test.
2. Create the production schema without deleting existing tables.
3. Add tenant/auth/grant tables and internal seed accounts.
4. Implement tenant-scoped project read/write APIs behind a feature flag.
5. Migrate known development projects explicitly to a development tenant. Records with unknown ownership remain inaccessible until assigned; do not guess.
6. Add object storage integration and migrate only test assets first.
7. Deploy worker in mock/staging mode, observe leases/recovery/metrics.
8. Switch the new UI project flow to the new APIs for internal users.
9. Disable legacy live routes in production; monitor attempted calls.
10. Run a tightly capped, explicitly authorized live smoke test in staging.
11. Enable private alpha only after the acceptance checklist passes.

### 11.2 Metrics and alerts

Capture at minimum:

- commands by status and tenant;
- plan time, queue wait, render latency, assembly/QC time;
- provider success/failure/capacity/wall/auth rates by provider and seat;
- provider credits reserved/spent/reconciled;
- job attempts, lease expiries, dead letters, and reassignments;
- assets uploaded, scanned, quarantined, deleted;
- delivery success/download errors;
- cross-tenant authorization denials;
- customer-visible ETA error versus actual completion;
- worker/API health and database/storage failures.

Alert on duplicate-submission suspicion, unbounded queue growth, unexpected spend, missing provider reconciliation, repeated wall/auth failures, cross-tenant access denial spikes, failed final QC, and worker lease expiry spikes.

### 11.3 Support playbooks

Write short operator instructions for:

1. customer cannot access a lifetime link;
2. payment completed but grant missing;
3. film stuck waiting for capacity;
4. provider reports wall/auth failure;
5. provider reports completion but media is missing/corrupt;
6. customer requests cancellation/refund/deletion;
7. final QC fails;
8. suspected data-isolation/security incident.

Each playbook must name the owner, safe action, audit record required, customer message template, and escalation threshold.

---

## 12. Implementation order and Definition of Done

### Milestone A — Safe product spine (P0)

Complete P0-01 through P0-10.

**Definition of done:**

- no unauthenticated or legacy route can spend production credits;
- payment/grant/tenant ownership exists and is tested;
- projects/assets/films persist across restart and are tenant-isolated;
- workers, not browsers, advance film jobs with atomic claims;
- the visible UI uses real persisted projects and does not fabricate ready media;
- mock artifacts cannot become customer deliveries;
- production configuration fails closed instead of silently using development defaults;
- every P0 regression test listed above passes in CI.

### Milestone B — Credible short-film studio beta (P1)

Complete script versions, show bible, plan approval, dailies/variants, a minimal timeline, audio/caption workflow, basic QC/master, cost/ETA/status, and operator/support tooling.

**Definition of done:**

A private customer can complete a **short** film with:

```text
authenticated purchase/grant
→ project
→ locked script
→ approved plan
→ durable rendering
→ dailies selection
→ timeline/picture lock
→ audio/captions
→ QC
→ protected delivery
```

The entire flow is recoverable after worker/API restart and has a traceable owner, policy snapshot, cost ledger, and audit history.

### Milestone C — Long-form readiness (P1/P2)

Before a three-hour promise, prove sequence-level planning, continuity, worker scaling, capacity planning, performance, economics, delivery storage, support workflow, and quality sampling on progressively larger films.

**Definition of done:**

- Use a staged evidence ladder: 3 clips → 1 minute → 5 minutes → 20 minutes → long-form pilot.
- Each level has measured provider cost, completion rate, re-render rate, average queue time, real ETA accuracy, storage cost, support load, and customer-quality review.
- A long-form pilot has a locked plan, explicit fair-use/budget policy, operator monitoring, and a manual escalation plan. It is not an uncontrolled customer self-serve experiment.

---

## 13. Documentation changes required

Update documentation as part of every implementation change. The current README/architecture/backend documentation describes conflicting stacks and stale provider assumptions.

Create or update the following documents:

| Document | Required content |
| --- | --- |
| `README.md` | Canonical app stack, local startup, test commands, explicit development/mock restrictions |
| `ARCHITECTURE.md` | Approved ADRs, system diagram, tenant boundaries, worker/data/media flow, source-of-truth decision |
| `docs/API.md` | Auth model, endpoint contracts, status/error semantics, idempotency requirements, OpenAPI link |
| `docs/DATA_MODEL.md` | Entity relationship diagram, ownership rules, retention, migrations |
| `docs/WORKER_OPERATIONS.md` | Worker launch, leasing, recovery, metrics, dead-letter handling |
| `docs/PROVIDER_CONTRACTS.md` | Versioned router contracts, idempotency, retry, capacity, and seat limitations |
| `docs/SECURITY_AND_RIGHTS.md` | Auth, media access, secret handling, consent/rights, deletion, incident path |
| `docs/PRODUCT_WORKFLOW.md` | Studio phases, approval gates, customer states, fair-use policy |
| `docs/RELEASE_CHECKLIST.md` | P0/P1 test evidence and go/no-go approval fields |

Mark all legacy paths and stale docs clearly. Do not leave a document implying that a simulated UI feature or a mock film is production-ready.

---

## 14. Final checklist for the implementer

Before stating that the product is ready for public paid use, answer **yes** to every question:

- [ ] Does every customer request authenticate and resolve a tenant?
- [ ] Can no tenant retrieve another tenant's projects, prompts, references, assets, renders, or delivery links?
- [ ] Does a verified payment create exactly one durable entitlement grant?
- [ ] Does the product enforce the published fair-use/concurrency policy server-side?
- [ ] Can no UI or legacy route submit a live render without server-side spend authorization?
- [ ] Does the browser only enqueue commands while workers do actual render/poll/assembly work?
- [ ] Can a worker restart or be duplicated without duplicate render spend?
- [ ] Are render attempts, provider IDs, costs, policy snapshots, and output provenance retained?
- [ ] Is mock media isolated, visibly synthetic, and impossible to deliver as production customer output?
- [ ] Do projects, scripts, plans, shots, dailies, timelines, and masters have version history and approval gates?
- [ ] Can an editor choose takes, trim/reorder safely, lock picture, add sound/captions, and run QC?
- [ ] Is final delivery private, expirable/revocable where appropriate, and audit logged?
- [ ] Are P0/P1 tests and a controlled staging E2E run passing?
- [ ] Are documentation, support playbooks, monitoring, backup/restore, and incident procedures current?

If any answer is no, describe the limitation honestly in the product and do not represent the system as a fully autonomous, unlimited, production film studio.
