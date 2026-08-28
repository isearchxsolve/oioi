"""Closed-SaaS account lifecycle and session persistence."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, new_bearer_token, token_digest, verify_password
from app.models.auth_session import AuthSession
from app.models.user import User


class OwnerBootstrapError(RuntimeError):
    """Raised only when a production server has no safe owner configuration."""


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL_RE.fullmatch(email) or len(email) > 255:
        raise ValueError("a valid email address is required")
    return email


def validate_new_password(password: str) -> None:
    if len(password) < 12 or len(password) > 128:
        raise ValueError("password must contain 12 to 128 characters")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def bootstrap_owner(session: AsyncSession) -> Optional[User]:
    """Create the configured owner only when no administrator exists yet.

    The seed password is never applied to an existing account, so it can be removed
    from deployment configuration immediately after the first successful startup.
    """
    owners = list((await session.scalars(select(User).where(User.is_superuser.is_(True)))).all())
    if len(owners) > 1:
        raise OwnerBootstrapError("database contains more than one administrator")
    if owners:
        return owners[0]
    if not settings.OWNER_EMAIL or not settings.OWNER_INITIAL_PASSWORD:
        if settings.APP_ENV.lower() in {"production", "prod"}:
            raise OwnerBootstrapError(
                "set OIOI_OWNER_EMAIL and OIOI_OWNER_INITIAL_PASSWORD before first production startup"
            )
        return None
    try:
        email = normalize_email(settings.OWNER_EMAIL)
        validate_new_password(settings.OWNER_INITIAL_PASSWORD)
    except ValueError as exc:
        raise OwnerBootstrapError(f"invalid owner bootstrap configuration: {exc}") from exc
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        existing.is_superuser = True
        existing.is_active = True
        await session.commit()
        return existing
    owner = User(
        id=str(uuid.uuid4()), email=email, name="Owner", is_active=True, is_superuser=True,
        hashed_password=hash_password(settings.OWNER_INITIAL_PASSWORD), provider="local",
    )
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    return owner


async def create_session(session: AsyncSession, user: User) -> tuple[str, AuthSession]:
    token = new_bearer_token()
    auth_session = AuthSession(
        id=str(uuid.uuid4()), user_id=user.id, token_hash=token_digest(token),
        expires_at=_now() + timedelta(hours=max(1, settings.AUTH_SESSION_TTL_HOURS)),
    )
    session.add(auth_session)
    await session.commit()
    await session.refresh(auth_session)
    return token, auth_session


async def current_user_for_token(session: AsyncSession, token: str) -> Optional[User]:
    now = _now()
    auth_session = await session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_digest(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if auth_session is None:
        return None
    user = await session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        return None
    auth_session.last_seen_at = now
    await session.commit()
    return user


async def revoke_token(session: AsyncSession, token: str) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == token_digest(token), AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await session.commit()


async def revoke_all_sessions(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await session.commit()
