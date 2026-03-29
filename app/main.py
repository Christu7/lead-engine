import sentry_sdk
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.logging_config import configure_logging

# Logging must be configured before any other imports that use loggers
configure_logging(settings.LOG_LEVEL)

from app.api.admin import router as admin_router  # noqa: E402
from app.api.custom_fields import router as custom_fields_router  # noqa: E402
from app.api.auth import router as auth_router  # noqa: E402
from app.api.companies import router as companies_router  # noqa: E402
from app.api.clients import router as clients_router  # noqa: E402
from app.api.dashboard import router as dashboard_router  # noqa: E402
from app.api.health import router as health_router  # noqa: E402
from app.api.leads import router as leads_router  # noqa: E402
from app.api.metrics import router as metrics_router  # noqa: E402
from app.api.routing import router as routing_router  # noqa: E402
from app.api.scoring import router as scoring_router  # noqa: E402
from app.api.settings import router as settings_router  # noqa: E402
from app.api.webhooks import router as webhooks_router  # noqa: E402
from app.core.exception_handlers import register_exception_handlers  # noqa: E402
from app.core.rate_limit import limiter, rate_limit_exceeded_handler  # noqa: E402
from app.middleware.body_limit import WebhookBodySizeLimitMiddleware  # noqa: E402
from app.middleware.request_logging import RequestLoggingMiddleware  # noqa: E402
from app.middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402

if settings.SENTRY_DSN:
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.DEBUG:
        if settings.SECRET_KEY == "change-me-in-production":
            raise RuntimeError(
                "SECRET_KEY is set to the default value. "
                "Set a strong random SECRET_KEY in your environment before deploying."
            )
        if len(settings.SECRET_KEY) < 32:
            raise RuntimeError(
                "SECRET_KEY must be at least 32 characters long. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if settings.ADMIN_PASSWORD == "changeme":
            raise RuntimeError(
                "ADMIN_PASSWORD is set to the default value. "
                "Set a strong ADMIN_PASSWORD in your environment before deploying."
            )
        if not settings.ENCRYPTION_KEY:
            raise RuntimeError(
                "ENCRYPTION_KEY is not set. "
                "Set a strong random ENCRYPTION_KEY in your environment before deploying."
            )
        if "localhost" in settings.BACKEND_URL:
            raise RuntimeError(
                "BACKEND_URL must not point to localhost in production. "
                "Set BACKEND_URL to your production backend URL."
            )
        if "localhost" in settings.FRONTEND_URL:
            raise RuntimeError(
                "FRONTEND_URL must not point to localhost in production. "
                "Set FRONTEND_URL to your production frontend URL."
            )
    yield


# Disable Swagger UI and OpenAPI schema in production — they expose the full
# API surface to anyone who discovers the URL.
_docs_url = "/docs" if settings.DEBUG else None
_redoc_url = "/redoc" if settings.DEBUG else None
_openapi_url = "/openapi.json" if settings.DEBUG else None

app = FastAPI(
    title="LeadEngine",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

register_exception_handlers(app)

# Rate limiting — limiter must be on app.state before SlowAPIMiddleware is added.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Middleware stack (add_middleware is LIFO — last added = outermost = first to process requests).
# Effective order: SecurityHeadersMiddleware → CORSMiddleware → SlowAPIMiddleware
#                  → WebhookBodySizeLimitMiddleware → RequestLoggingMiddleware → SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(WebhookBodySizeLimitMiddleware)
app.add_middleware(SlowAPIMiddleware)
if settings.DEBUG:
    # Dev: allow localhost origins only (never a wildcard)
    _cors_origins = ["http://localhost:3000", "http://localhost:5173"]
else:
    # Prod: parse ALLOWED_ORIGINS; reject wildcards to prevent credential leakage
    _cors_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if not _cors_origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS must be set in production. "
            "Provide a comma-separated list of allowed origins (no wildcards)."
        )
    if any("*" in o for o in _cors_origins):
        raise RuntimeError(
            "ALLOWED_ORIGINS must not contain wildcards. "
            "Specify exact origins (e.g. https://app.example.com)."
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(SecurityHeadersMiddleware, debug=settings.DEBUG)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(leads_router, prefix="/api")
app.include_router(companies_router, prefix="/api/companies", tags=["companies"])
app.include_router(routing_router, prefix="/api")
app.include_router(scoring_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(webhooks_router, prefix="/api")
app.include_router(custom_fields_router, prefix="/api")
