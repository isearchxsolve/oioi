"""Authenticated, non-spending provider view over the consumer catalogue."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.dependencies.auth import get_current_user
from app.models.user import User
from film_pipeline.clients import ChatPoolClient

router = APIRouter()


@router.get("/health")
async def provider_health_dashboard(user: User = Depends(get_current_user)):
    """Report the canonical route catalogue without probing or spending.

    A catalogue row is an advertised route, not proof of a graduated seat.  The
    durable film scheduler owns live admission and capacity decisions.
    """

    del user
    client = ChatPoolClient()
    try:
        catalogue = await client.models()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"canonical provider catalogue unavailable: {type(exc).__name__}",
        ) from exc
    finally:
        await client.aclose()

    rows = catalogue.get("data") or []
    routes = sorted({
        str(row.get("id"))
        for row in rows
        if isinstance(row, dict)
        and str(row.get("id") or "").startswith(("video/", "session-pool/"))
    })
    snapshot = [
        {
            "name": route.removeprefix("video/").removesuffix("/auto")
            if route.startswith("video/")
            else route,
            "route": route,
            "reachable": True,
        }
        for route in routes
    ]
    return {
        "status": "healthy",
        "active_providers": len(snapshot),
        "providers": snapshot,
        "transport": "http://127.0.0.1:8190/v1",
        "catalogue_only": True,
    }
