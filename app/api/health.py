from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import async_session
from app.core.redis import redis

router = APIRouter()


@router.get("/health")
async def health_check():
    checks = {"status": "healthy", "postgres": "ok", "redis": "ok"}

    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        checks["postgres"] = "unavailable"
        checks["status"] = "degraded"

    try:
        await redis.ping()
    except Exception:
        checks["redis"] = "unavailable"
        checks["status"] = "degraded"

    return checks
