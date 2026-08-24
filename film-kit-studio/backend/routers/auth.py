"""
Auth Router — Authentication endpoints for JWT and API keys.
"""

import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from auth import (
    create_access_token,
    verify_token,
    get_current_user,
    api_key_manager,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# REQUEST/RESPONSE MODELS
# ─────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])


class APIKeyResponse(BaseModel):
    key: str
    name: str
    scopes: list[str]
    created_at: str


class APIKeyListResponse(BaseModel):
    keys: list[dict]


# ─────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT access token.
    
    Note: In production, implement proper password hashing (bcrypt/argon2)
    and user lookup from database. This is a placeholder implementation.
    """
    # Placeholder: In production, verify against database with hashed passwords
    # For demo purposes, accept any non-empty credentials
    if not request.email or not request.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email and password required",
        )

    # Create user payload (in production, fetch from DB)
    user_payload = {
        "sub": request.email,
        "email": request.email,
        "roles": ["user"],
        "scopes": ["read", "write"],
    }

    access_token = create_access_token(user_payload)
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/token", response_model=TokenResponse)
async def create_token(request: LoginRequest):
    """OAuth2 compatible token endpoint."""
    if not request.email or not request.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email and password required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_payload = {
        "sub": request.email,
        "email": request.email,
        "roles": ["user"],
        "scopes": ["read", "write"],
    }

    access_token = create_access_token(user_payload)
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "email": request.email,
            "roles": ["user"],
            "scopes": ["read", "write"],
        },
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """Refresh access token."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Create new token with same payload (minus exp/iat)
    new_payload = {k: v for k, v in current_user.items() if k not in ("exp", "iat")}
    access_token = create_access_token(new_payload)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user info from token."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return current_user


@router.post("/logout")
async def logout():
    """Logout endpoint (client should discard token)."""
    return {"message": "Logged out successfully"}


# ─────────────────────────────────────────────────────────────────
# API KEY MANAGEMENT
# ─────────────────────────────────────────────────────────────────

@router.post("/api-keys", response_model=APIKeyResponse, status_code=201)
async def create_api_key(
    request: APIKeyCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new API key."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    key = api_key_manager.generate_key(
        name=request.name,
        scopes=request.scopes,
    )

    return APIKeyResponse(
        key=key,
        name=request.name,
        scopes=request.scopes,
        created_at=datetime.utcnow().isoformat(),
    )


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_api_keys(current_user: dict = Depends(get_current_user)):
    """List all API keys for current user."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    keys = api_key_manager.list_keys()
    return APIKeyListResponse(keys=keys)


@router.delete("/api-keys/{key_prefix}")
async def revoke_api_key(key_prefix: str, current_user: dict = Depends(get_current_user)):
    """Revoke an API key."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Find full key from prefix
    revoked = False
    for key in api_key_manager.keys:
        if key.startswith(key_prefix):
            revoked = api_key_manager.revoke_key(key)
            break

    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")

    return {"message": "API key revoked", "key_prefix": key_prefix}


# ─────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────

@router.get("/health")
async def auth_health():
    """Auth service health check."""
    return {"status": "ok", "service": "auth"}