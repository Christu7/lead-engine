import time
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import async_session
from app.core.redis import redis
from app.core.state import APP_START_TIME

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/health/detailed")
async def detailed_health_check():
    checks: dict = {}

    t = time.perf_counter()
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = {"status": "ok", "response_ms": round((time.perf_counter() - t) * 1000, 2)}
    except Exception as exc:
        checks["db"] = {
            "status": "unavailable",
            "error": str(exc),
            "response_ms": round((time.perf_counter() - t) * 1000, 2),
        }

    t = time.perf_counter()
    try:
        await redis.ping()
        checks["redis"] = {"status": "ok", "response_ms": round((time.perf_counter() - t) * 1000, 2)}
    except Exception as exc:
        checks["redis"] = {
            "status": "unavailable",
            "error": str(exc),
            "response_ms": round((time.perf_counter() - t) * 1000, 2),
        }

    overall = "ok" if all(c["status"] == "ok" for c in checks.values()) else "degraded"
    uptime_seconds = round((datetime.now(timezone.utc) - APP_START_TIME).total_seconds())

    return {"status": overall, "checks": checks, "uptime_seconds": uptime_seconds}
