"""Closed SaaS authentication and owner-operated account administration."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import get_current_user, require_admin
from app.core.database import get_session
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.project import Project
from app.models.asset import Asset
from app.services.auth_service import (
    create_session,
    normalize_email,
    revoke_all_sessions,
    revoke_token,
    validate_new_password,
)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdateRequest(BaseModel):
    email: Optional[str] = Field(default=None, min_length=3, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=512)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AdminUserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=512)


class AdminUserUpdateRequest(BaseModel):
    email: Optional[str] = Field(default=None, min_length=3, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=512)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=128)


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "is_admin": user.is_superuser,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _bearer_from_request(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" else ""


async def _customer_history(session: AsyncSession, user: User) -> dict:
    """Operator-safe complete customer inventory; binary media is never inlined."""
    projects = list((await session.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
    )).all())
    project_ids = [project.id for project in projects]
    assets = []
    if project_ids:
        assets = list((await session.scalars(
            select(Asset).where(Asset.project_id.in_(project_ids)).order_by(Asset.created_at.desc())
        )).all())
    # Import lazily to avoid API-router module initialisation cycles.
    from app.api.v1.endpoints.films import _services

    films = _services.store.films_for_owner(user.id)
    return {
        "user": _user_payload(user),
        "projects": [
            {"id": project.id, "name": project.name, "status": project.status, "created_at": project.created_at,
             "updated_at": project.updated_at}
            for project in projects
        ],
        "assets": [
            {"id": asset.id, "project_id": asset.project_id, "type": asset.type, "name": asset.name,
             "url": asset.url, "duration": asset.duration, "created_at": asset.created_at,
             "metadata": asset.metadata_json}
            for asset in assets
        ],
        "films": films,
        "storage": {
            "artifact_bytes": sum(int((film.get("artifact") or {}).get("stored_bytes") or 0) for film in films),
            "artifact_count": sum(1 for film in films if film.get("artifact")),
        },
    }


@router.get("/bootstrap-status")
async def bootstrap_status(session: AsyncSession = Depends(get_session)):
    """Safe setup signal for the operator UI; it never exposes owner identity."""
    owner = await session.scalar(select(User.id).where(User.is_superuser.is_(True)))
    return {"public_signup": False, "owner_configured": owner is not None}


@router.post("/signup")
async def signup_is_disabled():
    """An explicit answer prevents accidental reopening of customer registration."""
    raise HTTPException(status_code=403, detail="public signup is disabled; contact the studio operator")


@router.post("/login")
async def login(request: LoginRequest, session: AsyncSession = Depends(get_session)):
    try:
        email = normalize_email(request.email)
    except ValueError:
        # Do not reveal which half of an invalid credential pair failed.
        raise HTTPException(status_code=401, detail="invalid email or password")
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="invalid email or password")
    token, auth_session = await create_session(session, user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": auth_session.expires_at,
        "user": _user_payload(user),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    token = _bearer_from_request(request)
    if token:
        await revoke_token(session, token)


@router.get("/me")
async def get_my_profile(user: User = Depends(get_current_user)):
    return _user_payload(user)


@router.patch("/me")
async def update_my_profile(
    request: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if request.email is not None:
        try:
            email = normalize_email(request.email)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        duplicate = await session.scalar(select(User.id).where(User.email == email, User.id != user.id))
        if duplicate:
            raise HTTPException(status_code=409, detail="a user with this email already exists")
        user.email = email
    if request.name is not None:
        user.name = request.name.strip() or None
    if request.avatar_url is not None:
        user.avatar_url = request.avatar_url.strip() or None
    await session.commit()
    await session.refresh(user)
    return _user_payload(user)


@router.post("/me/password")
async def change_my_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    try:
        validate_new_password(request.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    current_user.hashed_password = hash_password(request.new_password)
    await session.commit()
    # A password change is a security boundary: every browser/API session must re-login.
    await revoke_all_sessions(session, current_user.id)
    return {"changed": True, "reauthentication_required": True}


@router.get("/users")
async def list_users(
    _: User = Depends(require_admin), session: AsyncSession = Depends(get_session)
):
    users = list((await session.scalars(select(User).order_by(User.created_at.desc()))).all())
    return {"users": [_user_payload(user) for user in users]}


@router.get("/users/{user_id}/history")
async def get_customer_history(
    user_id: str,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return await _customer_history(session, user)


@router.get("/history")
async def get_all_customer_history(
    _: User = Depends(require_admin), session: AsyncSession = Depends(get_session)
):
    users = list((await session.scalars(select(User).order_by(User.created_at.desc()))).all())
    histories = [await _customer_history(session, user) for user in users]
    return {"users": histories}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: AdminUserCreateRequest,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        email = normalize_email(request.email)
        validate_new_password(request.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="a user with this email already exists")
    user = User(
        id=str(uuid.uuid4()), email=email, name=(request.name or "").strip() or None,
        avatar_url=(request.avatar_url or "").strip() or None, hashed_password=hash_password(request.password),
        is_active=True, is_superuser=False, provider="local",
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="a user with this email already exists") from exc
    await session.refresh(user)
    return _user_payload(user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    request: AdminUserUpdateRequest,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.is_superuser:
        raise HTTPException(status_code=403, detail="the sole administrator must use /auth/me")
    try:
        if request.email is not None:
            email = normalize_email(request.email)
            duplicate = await session.scalar(select(User.id).where(User.email == email, User.id != user.id))
            if duplicate:
                raise HTTPException(status_code=409, detail="a user with this email already exists")
            user.email = email
        if request.password is not None:
            validate_new_password(request.password)
            user.hashed_password = hash_password(request.password)
            await revoke_all_sessions(session, user.id)
        if request.name is not None:
            user.name = request.name.strip() or None
        if request.avatar_url is not None:
            user.avatar_url = request.avatar_url.strip() or None
        if request.is_active is not None:
            user.is_active = request.is_active
            if not request.is_active:
                await revoke_all_sessions(session, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="a user with this email already exists") from exc
    await session.refresh(user)
    return _user_payload(user)
