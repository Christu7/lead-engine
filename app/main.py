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
from app.middleware.request_logging import RequestLoggingMiddleware  # noqa: E402

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
        if settings.ADMIN_PASSWORD == "changeme":
            raise RuntimeError(
                "ADMIN_PASSWORD is set to the default value. "
                "Set a strong ADMIN_PASSWORD in your environment before deploying."
            )
    yield


app = FastAPI(title="LeadEngine", version="0.1.0", lifespan=lifespan)

register_exception_handlers(app)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
