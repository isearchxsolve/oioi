"""Safety gate for retired synchronous/demo routes."""
from fastapi import HTTPException

from app.core.config import settings


def require_legacy_demo_mode() -> None:
    """Allow old spend-capable routes only under an explicit local opt-in.

    The replacement is the durable ``/api/v1/films`` API, which persists an
    idempotent graph before any scheduler work.  A 410 is intentional: redirecting a
    stale POST could silently turn an old browser request into a billable render.
    """
    if settings.APP_ENV.casefold() == "development" and settings.ENABLE_LEGACY_DEMO_ROUTES:
        return
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_route_retired",
            "replacement": "/api/v1/films",
            "message": "This direct generation route is retired; use durable film admission instead.",
        },
    )
