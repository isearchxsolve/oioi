"""Permanent safety gate for retired synchronous/demo routes."""
from fastapi import HTTPException


def require_legacy_demo_mode() -> None:
    """Reject every retired direct-generation route.

    The replacement is the durable ``/api/v1/films`` API, which persists an
    idempotent graph before any scheduler work.  A 410 is intentional: redirecting a
    stale POST could silently turn an old browser request into a billable render.

    Older releases accepted ``ENABLE_LEGACY_DEMO_ROUTES`` in development. That
    switch is deliberately no longer honored: an opt-in direct-provider path is
    still a second execution lineage and violates the single consumer endpoint
    contract. Local tests should use the deterministic film-pipeline fakes.
    """
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_route_retired",
            "replacement": "/api/v1/films",
            "message": "This direct generation route is retired; use durable film admission instead.",
        },
    )
