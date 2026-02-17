from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.clients import router as clients_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.api.routing import router as routing_router
from app.api.scoring import router as scoring_router
from app.api.settings import router as settings_router
from app.api.webhooks import router as webhooks_router

app = FastAPI(title="LeadEngine", version="0.1.0")

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(leads_router, prefix="/api")
app.include_router(routing_router, prefix="/api")
app.include_router(scoring_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(webhooks_router, prefix="/api")
