import json
import logging
import time

import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import decode_access_token

logger = logging.getLogger("api.requests")

_SENSITIVE_SUBSTRINGS = ("key", "secret", "password", "token")


def _redact_body(body: object) -> object:
    """Recursively redact dict values whose keys contain sensitive substrings."""
    if isinstance(body, dict):
        return {
            k: "[REDACTED]" if any(s in k.lower() for s in _SENSITIVE_SUBSTRINGS) else _redact_body(v)
            for k, v in body.items()
        }
    if isinstance(body, list):
        return [_redact_body(item) for item in body]
    return body


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Health checks are too noisy — skip them
        if request.url.path.startswith("/api/health"):
            return await call_next(request)

        # Pre-read body for POST/PATCH so we can log it on failure.
        # request.body() caches the bytes in Starlette, so the handler
        # can still read it normally afterwards.
        body_bytes = b""
        if request.method in ("POST", "PATCH"):
            ct = request.headers.get("content-type", "")
            if "multipart" not in ct and "application/x-www-form-urlencoded" not in ct:
                body_bytes = await request.body()

        # Decode JWT (no DB hit) to enrich logs and Sentry context
        token_data = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token_data = decode_access_token(auth_header[7:])

        if token_data:
            sentry_sdk.set_user({"id": str(token_data.user_id), "email": token_data.email})
            sentry_sdk.set_tag("client_id", str(token_data.active_client_id or "none"))

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        extra: dict = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }
        if token_data:
            extra["user_id"] = token_data.user_id
            extra["client_id"] = token_data.active_client_id

        # Only log request body on failure, and only for mutation methods
        if body_bytes and response.status_code >= 400:
            try:
                extra["request_body"] = _redact_body(json.loads(body_bytes))
            except Exception:
                extra["request_body"] = body_bytes.decode("utf-8", errors="replace")[:500]

        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            "%s %s %d",
            request.method,
            request.url.path,
            response.status_code,
            extra=extra,
        )
        return response
