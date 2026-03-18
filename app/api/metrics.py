from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.redis import redis
from app.core.state import APP_START_TIME
from app.models.lead import EnrichmentLog, Lead, RoutingLog
from app.services.enrichment.queue import QUEUE_KEY

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(require_admin)])


@router.get("")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h = now - timedelta(hours=24)

    # Leads created today (all clients; admin-only endpoint)
    leads_today = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.created_at >= today_start)
        )
    ).scalar() or 0

    # Redis queue depth
    enrichment_queue_size = await redis.llen(QUEUE_KEY)

    # Routing stats over the last 24 h
    routing_row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(RoutingLog.success.is_(True)).label("success"),
                func.count().filter(RoutingLog.success.is_(False)).label("failed"),
            )
            .select_from(RoutingLog)
            .where(RoutingLog.created_at >= last_24h)
        )
    ).one()

    # Leads currently pending/enriching (effectively "pending routing")
    pending_count = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.enrichment_status.in_(["pending", "enriching"]))
        )
    ).scalar() or 0

    routing_stats_24h = {
        "success": routing_row.success,
        "failed": routing_row.failed,
        "pending": pending_count,
    }

    # Timestamps of most recent activity
    last_enrichment_at = (
        await db.execute(select(func.max(EnrichmentLog.created_at)))
    ).scalar()

    last_routing_at = (
        await db.execute(select(func.max(RoutingLog.created_at)))
    ).scalar()

    uptime_seconds = round((now - APP_START_TIME).total_seconds())

    return {
        "leads_today": leads_today,
        "enrichment_queue_size": enrichment_queue_size,
        "routing_stats_24h": routing_stats_24h,
        "last_enrichment_at": last_enrichment_at.isoformat() if last_enrichment_at else None,
        "last_routing_at": last_routing_at.isoformat() if last_routing_at else None,
        "system_uptime_seconds": uptime_seconds,
    }
