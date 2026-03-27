"""Rate limiting via slowapi.

Key functions:
- _get_user_id_key: JWT user_id, falls back to IP for unauthenticated routes
- get_api_key_rate_key: hashed X-Api-Key header, falls back to IP

The Limiter is initialised with default_limits=["300/minute"] so every
endpoint that has no specific decorator gets 300 req/min per user (IP
fallback for unauthenticated routes).  Individual endpoints override this
with @limiter.limit() decorators.
"""
import hashlib
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_user_id_key(request: Request) -> str:
    """Rate limit key: user_id extracted from Bearer JWT, falling back to IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            # Lazy import to avoid circular dependency (security → config → rate_limit)
            from app.core.security import decode_access_token
            data = decode_access_token(token)
            if data:
                return f"user:{data.user_id}"
        except Exception:
            pass
    return get_remote_address(request)


def get_api_key_rate_key(request: Request) -> str:
    """Rate limit key: hashed X-Api-Key header, falling back to IP.

    The raw key is never stored in Redis — only a 24-char SHA-256 prefix.
    """
    api_key = request.headers.get("x-api-key")
    if api_key:
        hashed = hashlib.sha256(api_key.encode()).hexdigest()[:24]
        return f"apikey:{hashed}"
    return get_remote_address(request)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a structured 429 response with Retry-After."""
    retry_after = "60"
    if exc.headers:
        retry_after = exc.headers.get("Retry-After", "60")
    try:
        retry_seconds = int(retry_after)
    except (ValueError, TypeError):
        retry_seconds = 60

    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_seconds)},
        content={
            "error": "RateLimitExceeded",
            "message": f"Too many requests. Try again in {retry_seconds} seconds.",
            "retry_after": retry_seconds,
        },
    )


limiter = Limiter(
    key_func=_get_user_id_key,
    default_limits=["300/minute"],
    storage_uri=settings.REDIS_URL,
)
