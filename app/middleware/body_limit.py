"""ASGI middleware: reject webhook requests whose Content-Length exceeds 1 MB.

Placed early in the middleware stack so oversized payloads are rejected before
any body parsing (logging, signature verification, JSON decode) occurs.

Only the Content-Length header is checked (fast path). Requests sent with
chunked transfer encoding and no Content-Length header are not covered here;
those are considered acceptable for the current threat model because all
well-behaved webhook senders (Apollo, Typeform, etc.) send Content-Length.
"""
from fastapi.responses import JSONResponse

_WEBHOOK_MAX_BYTES = 1 * 1024 * 1024  # 1 MB


class WebhookBodySizeLimitMiddleware:
    """Rejects /api/webhooks/* requests whose Content-Length exceeds 1 MB."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path", "").startswith("/api/webhooks"):
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            cl_bytes = headers.get(b"content-length")
            if cl_bytes is not None:
                try:
                    if int(cl_bytes) > _WEBHOOK_MAX_BYTES:
                        response = JSONResponse(
                            status_code=413,
                            content={
                                "error": "PayloadTooLarge",
                                "message": (
                                    "Webhook payload too large. "
                                    f"Maximum size is {_WEBHOOK_MAX_BYTES // 1024 // 1024} MB."
                                ),
                            },
                        )
                        await response(scope, receive, send)
                        return
                except ValueError:
                    pass
        await self.app(scope, receive, send)
