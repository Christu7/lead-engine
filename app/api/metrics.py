from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_token_data, require_admin
from app.core.redis import redis
from app.core.security import TokenData
from app.core.state import APP_START_TIME
from app.models.lead import EnrichmentLog, Lead, RoutingLog
from app.models.user import User, UserClient
from app.services.task_queue import TASK_QUEUE_KEY

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    client_id: int | None = Query(None, description="Filter metrics to a specific client"),
):
    # MT-2: non-superadmin admins may only query clients they belong to.
    if client_id is not None and current_user.role != "superadmin":
        access_check = await db.execute(
            select(UserClient).where(
                UserClient.user_id == current_user.id,
                UserClient.client_id == client_id,
            )
        )
        if access_check.scalar_one_or_none() is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="You do not have access to that client")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h = now - timedelta(hours=24)

    # Build base filters — optionally scoped to a single client
    lead_filters = [Lead.created_at >= today_start]
    routing_filters = [RoutingLog.created_at >= last_24h]
    pending_filters = [Lead.enrichment_status.in_(["pending", "enriching"])]
    enrich_max_filters = []
    routing_max_filters = []

    if client_id is not None:
        lead_filters.append(Lead.client_id == client_id)
        routing_filters.append(RoutingLog.client_id == client_id)
        pending_filters.append(Lead.client_id == client_id)
        enrich_max_filters.append(EnrichmentLog.client_id == client_id)
        routing_max_filters.append(RoutingLog.client_id == client_id)

    # Leads created today
    leads_today = (
        await db.execute(
            select(func.count()).select_from(Lead).where(*lead_filters)
        )
    ).scalar() or 0

    # Redis queue depth (global — not filterable by client)
    enrichment_queue_size = await redis.zcard(TASK_QUEUE_KEY)

    # Routing stats over the last 24 h
    routing_row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(RoutingLog.success.is_(True)).label("success"),
                func.count().filter(RoutingLog.success.is_(False)).label("failed"),
            )
            .select_from(RoutingLog)
            .where(*routing_filters)
        )
    ).one()

    # Leads currently pending/enriching
    pending_count = (
        await db.execute(
            select(func.count()).select_from(Lead).where(*pending_filters)
        )
    ).scalar() or 0

    routing_stats_24h = {
        "success": routing_row.success,
        "failed": routing_row.failed,
        "pending": pending_count,
    }

    # Timestamps of most recent activity
    enrich_max_q = select(func.max(EnrichmentLog.created_at))
    if enrich_max_filters:
        enrich_max_q = enrich_max_q.where(*enrich_max_filters)
    last_enrichment_at = (await db.execute(enrich_max_q)).scalar()

    routing_max_q = select(func.max(RoutingLog.created_at))
    if routing_max_filters:
        routing_max_q = routing_max_q.where(*routing_max_filters)
    last_routing_at = (await db.execute(routing_max_q)).scalar()

    uptime_seconds = round((now - APP_START_TIME).total_seconds())

    return {
        "leads_today": leads_today,
        "enrichment_queue_size": enrichment_queue_size,
        "routing_stats_24h": routing_stats_24h,
        "last_enrichment_at": last_enrichment_at.isoformat() if last_enrichment_at else None,
        "last_routing_at": last_routing_at.isoformat() if last_routing_at else None,
        "system_uptime_seconds": uptime_seconds,
    }
