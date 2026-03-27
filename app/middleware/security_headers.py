"""Middleware that attaches security-related HTTP response headers to every response.

In production (debug=False):
- Strict-Transport-Security is set (requires HTTPS termination at nginx/LB).
- Content-Security-Policy is strict: default-src 'none'.

In development (debug=True):
- HSTS is omitted (HTTP is fine in dev).
- CSP is relaxed so Swagger UI's CDN scripts and inline styles work.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Relaxed CSP that allows Swagger UI (served from cdn.jsdelivr.net)
_DEV_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net"
)

# Strict CSP for a pure-JSON API (no HTML served in prod)
_PROD_CSP = "default-src 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    def __init__(self, app, debug: bool = False) -> None:
        super().__init__(app)
        self.debug = debug

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = _DEV_CSP if self.debug else _PROD_CSP

        if not self.debug:
            # Only set HSTS in production where HTTPS is guaranteed
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
