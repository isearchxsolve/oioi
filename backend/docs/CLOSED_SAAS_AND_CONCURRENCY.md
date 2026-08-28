# OiiOii closed SaaS model and concurrency readiness

## Operating model implemented

OiiOii is now a closed, owner-operated film-kit SaaS:

1. There is no public registration. `POST /api/v1/auth/signup` always returns `403`.
2. On the first production start, the service requires `OIOI_OWNER_EMAIL` and
   `OIOI_OWNER_INITIAL_PASSWORD`. It creates one active local owner with administrator rights.
   The seed password is used only when no administrator exists and is never reapplied, so remove
   it from the deployment environment immediately after first sign-in.
3. The owner creates paid customer accounts through `POST /api/v1/auth/users`. This route always
   creates a standard user; its request schema has no administrator flag.
4. Only the sole owner can list, create, edit, activate/deactivate, or reset customer accounts.
   The administrator record cannot be changed through the customer-management endpoint. The owner
   uses `/api/v1/auth/me` and `/api/v1/auth/me/password` for their own profile/password.
5. Passwords use salted `scrypt`; opaque 48-byte bearer credentials are returned only at login and
   only a SHA-256 digest is persisted. Logout, administrator deactivation/reset, and a user’s own
   password change revoke relevant sessions.
6. All studio routes (chat, generation, projects, pipeline, library, films, model/style/provider
   catalogue, jobs, and agency routes) require `Authorization: Bearer <access_token>`. Health and
   the safe owner-bootstrap status are deliberately public.

## Tenant boundaries implemented

* Projects now use the persistent SQLAlchemy `projects.user_id` relationship instead of the old
  in-process dictionary. List/read/update are filtered by the authenticated owner.
* A new durable `film_owners` table binds each API-admitted film to its account. Reads and scheduler
  ticks return `404` for another customer. Film idempotency keys now include the account scope, so
  identical briefs from different customers cannot replay one graph.
* Chat sessions, saved styles, generated character/scene library entries, uploaded character
  references, and their retrieval route are account-scoped. Local clip discovery is disabled in
  closed-SaaS mode because historical files have no trustworthy owner metadata.

## Required deployment configuration

Use `backend/.env.example` as the non-secret template. In the real deployment environment set:

```text
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://.../oioi
OIOI_CLOSED_SAAS_MODE=true
OIOI_OWNER_EMAIL=your-private-owner-email
OIOI_OWNER_INITIAL_PASSWORD=a-unique-password-of-at-least-12-characters
OIOI_AUTH_SESSION_TTL_HOURS=168
```

Do not commit the real `.env`. After the first successful owner login, remove
`OIOI_OWNER_INITIAL_PASSWORD` from the environment manager and retain the owner password only in
the approved password manager. A production process with no owner and no bootstrap values fails
startup rather than accidentally exposing an unowned workspace.

## API workflow

1. Sign in as owner: `POST /api/v1/auth/login` with email/password.
2. Put the returned `access_token` in `Authorization: Bearer ...`.
3. Create a paid customer: `POST /api/v1/auth/users` with `email`, `password`, optional `name`,
   and optional `avatar_url`.
4. Give the customer those credentials through the agreed off-platform channel. They sign in at
   `/api/v1/auth/login`; they cannot sign up or create another user.
5. The owner updates their own profile with `PATCH /api/v1/auth/me` and changes their own password
   with `POST /api/v1/auth/me/password`.

## Concurrent-request assessment: honest current state

### Safe today

The FastAPI service is asynchronous for provider I/O. The durable film scheduler uses SQLite WAL,
`BEGIN IMMEDIATE`, stable render job keys, and a durable `submitting` state. Concurrent `tick`
calls for the same film therefore have a single winner for each render submission; the loser sees
the already-claimed job and cannot purchase a duplicate clip. The scheduler also has explicit
submission, materialization, fallback, per-provider, and per-seat limits.

The new account/session/project writes are database transactions, so normal simultaneous logins,
customer creation attempts, and project operations have database-level uniqueness/ownership rules.

### Not yet safe to claim as horizontally scalable SaaS

This repository is **not yet ready for multi-worker or multi-host paid traffic** without the
following infrastructure work:

| Gap | Why it matters under concurrency | Required production change |
| --- | --- | --- |
| Default database is SQLite | SQLite serializes writers and the local path is not shareable across hosts. | Run PostgreSQL for all application data; keep the FilmJobStore on a single worker until it too is migrated or give it a shared transactional store. |
| Process-local chat/library/pipeline state | A request sent to another Uvicorn worker will not see that worker’s memory. | Move chat sessions, library metadata, and pipeline state to PostgreSQL/Redis, then remove the in-memory maps. |
| Local artifact paths | Multiple hosts do not share `storage/` or film artifacts. | Store artifacts in S3/GCS/MinIO, record object keys in the database, and issue tenant-authorized download URLs. |
| In-process scheduler | Two application processes can each schedule; SQLite protects a single file but is not a distributed job queue. | Use one scheduler worker/leader or a PostgreSQL-backed queue with advisory locks and idempotency keys. |
| Provider capacity is finite | Concurrent customer requests can still exhaust the 4-seat/credit upstream pool. | Add per-tenant quotas, a durable queue, provider budget reservations, retry visibility, and admission estimates. |
| No durable per-user login/generation limit | A customer or attacker can still concentrate requests against the local process or finite provider pool. | Add route-level login limits and user-ID plus IP quotas backed by Redis. |

### Practical conclusion

**Current answer:** OiiOii can safely serve concurrent HTTP requests in one process and prevents
duplicate clip submission for concurrent ticks of the same durable film. It is suitable for a
small, single-operator/single-worker closed beta after setting PostgreSQL for accounts/projects.
It is **not** yet a scale-out SaaS platform; run one Uvicorn worker and one scheduler owner until
the six changes above are complete. The remaining work is entirely on the OiiOii deployment and
application side, not dependent on live video generation providers.

## Verification performed

`pytest backend/tests/test_closed_saas_auth.py -q` verifies closed signup, owner account creation,
customer privilege denial, project isolation, profile updates, password-session revocation, and
fresh-password login. The existing authenticated endpoint regression suite also passes.
