"""
Authentication & Security Module

Provides JWT-based authentication, API key management, rate limiting,
and input sanitization for the Film Kit Studio API.
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from functools import wraps

import jwt
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import settings


# ─────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────

SECRET_KEY = settings.jwt_secret_key or secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
API_KEY_PREFIX = "fk_"

security = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────────
# JWT TOKEN MANAGEMENT
# ─────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[dict]:
    """Extract current user from JWT token."""
    if not credentials:
        return None
    return verify_token(credentials.credentials)


# ─────────────────────────────────────────────────────────────────
# API KEY MANAGEMENT
# ─────────────────────────────────────────────────────────────────

class APIKeyManager:
    """Manage API keys for external access."""

    def __init__(self):
        self.keys: Dict[str, Dict[str, Any]] = {}

    def generate_key(self, name: str, scopes: list[str] = None) -> str:
        """Generate a new API key."""
        key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        self.keys[key] = {
            "name": name,
            "scopes": scopes or ["read", "write"],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None,
            "active": True,
        }
        return key

    def validate_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Validate an API key and return its info."""
        if key not in self.keys:
            return None
        key_info = self.keys[key]
        if not key_info.get("active", False):
            return None
        key_info["last_used"] = datetime.utcnow().isoformat()
        return key_info

    def revoke_key(self, key: str) -> bool:
        """Revoke an API key."""
        if key in self.keys:
            self.keys[key]["active"] = False
            return True
        return False

    def list_keys(self) -> list[Dict[str, Any]]:
        """List all API keys (without the actual key)."""
        return [
            {**info, "key": key[:8] + "..." + key[-4:]}
            for key, info in self.keys.items()
        ]


api_key_manager = APIKeyManager()


# ─────────────────────────────────────────────────────────────────
# RATE LIMITING
# ─────────────────────────────────────────────────────────────────

class RateLimiter:
    """Simple in-memory rate limiter with sliding window."""

    def __init__(self):
        self.requests: Dict[str, list[float]] = {}
        self.default_limit = 60  # requests per minute
        self.default_window = 60  # seconds

    def _cleanup_old_requests(self, key: str, window: float):
        """Remove requests outside the time window."""
        now = time.time()
        if key in self.requests:
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if now - req_time < window
            ]

    def is_allowed(self, key: str, limit: int = None, window: float = None) -> bool:
        """Check if request is allowed under rate limit."""
        limit = limit or self.default_limit
        window = window or self.default_window
        now = time.time()

        self._cleanup_old_requests(key, window)

        if key not in self.requests:
            self.requests[key] = []

        if len(self.requests[key]) >= limit:
            return False

        self.requests[key].append(now)
        return True

    def get_remaining(self, key: str, limit: int = None, window: float = None) -> int:
        """Get remaining requests in current window."""
        limit = limit or self.default_limit
        self._cleanup_old_requests(key, window or self.default_window)
        return max(0, limit - len(self.requests.get(key, [])))


rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware."""

    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        key = f"ip:{client_ip}"

        # Different limits for different paths
        if request.url.path.startswith("/api/director"):
            limit, window = 10, 60  # 10 req/min for director
        elif request.url.path.startswith("/api/training"):
            limit, window = 5, 60  # 5 req/min for training
        else:
            limit, window = 60, 60  # 60 req/min default

        if not rate_limiter.is_allowed(key, limit, window):
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(int(window))}
            )

        # Add rate limit headers
        response = await call_next(request)
        remaining = rate_limiter.get_remaining(key, limit, window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response


# ─────────────────────────────────────────────────────────────────
# INPUT SANITIZATION
# ─────────────────────────────────────────────────────────────────

import html
import re
from typing import Any

# Patterns for dangerous input
SCRIPT_PATTERN = re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL)
STYLE_PATTERN = re.compile(r'<style[^>]*>.*?</style>', re.IGNORECASE | re.DOTALL)
IFRAME_PATTERN = re.compile(r'<iframe[^>]*>.*?</iframe>', re.IGNORECASE | re.DOTALL)
EVENT_HANDLER_PATTERN = re.compile(r'on\w+\s*=', re.IGNORECASE)
JAVASCRIPT_URL_PATTERN = re.compile(r'javascript:', re.IGNORECASE)
DATA_URL_PATTERN = re.compile(r'data:', re.IGNORECASE)


def sanitize_html(text: str) -> str:
    """Sanitize HTML input to prevent XSS."""
    if not isinstance(text, str):
        return text

    # Remove dangerous tags and attributes
    text = SCRIPT_PATTERN.sub('', text)
    text = STYLE_PATTERN.sub('', text)
    text = IFRAME_PATTERN.sub('', text)
    text = EVENT_HANDLER_PATTERN.sub('', text)
    text = JAVASCRIPT_URL_PATTERN.sub('', text)
    text = DATA_URL_PATTERN.sub('', text)

    # HTML escape remaining content
    return html.escape(text)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    # Remove path components
    filename = os.path.basename(filename)
    # Remove dangerous characters
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', filename)
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    return filename


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize all string values in a dict."""
    if not isinstance(data, dict):
        return data

    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_html(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_html(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class SanitizeMiddleware(BaseHTTPMiddleware):
    """Middleware to sanitize request body."""

    async def dispatch(self, request: Request, call_next):
        # Only sanitize JSON bodies
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                body = await request.body()
                if body:
                    import json
                    try:
                        data = json.loads(body)
                        sanitized = sanitize_dict(data)
                        # Note: Can't easily modify request body in Starlette
                        # This would need request._body replacement
                    except json.JSONDecodeError:
                        pass

        return await call_next(request)


# ─────────────────────────────────────────────────────────────────
# DEPENDENCY INJECTION HELPERS
# ─────────────────────────────────────────────────────────────────

def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[dict]:
    """Get current user if token provided, otherwise None."""
    if not credentials:
        return None
    try:
        return verify_token(credentials.credentials)
    except HTTPException:
        return None


def require_scopes(*required_scopes: str):
    """Dependency factory for requiring specific scopes."""
    def dependency(user: dict = Depends(get_current_user_optional)) -> dict:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        user_scopes = user.get("scopes", [])
        for scope in required_scopes:
            if scope not in user_scopes:
                raise HTTPException(status_code=403, detail=f"Scope '{scope}' required")
        return user
    return dependency


def require_admin(user: dict = Depends(get_current_user_optional)) -> dict:
    """Require admin role."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if "admin" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ─────────────────────────────────────────────────────────────────
# SECURITY HEADERS MIDDLEWARE
# ─────────────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' wss: https:; "
            "frame-ancestors 'none';"
        )
        return response