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
from app.models.provider_usage_log import ProviderUsageLog
from app.models.user import User, UserClient
from app.services.task_queue import TASK_QUEUE_KEY

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    token_data: TokenData = Depends(get_token_data),
    client_id: int | None = Query(None, description="Filter metrics to a specific client"),
):
    from fastapi import HTTPException

    # Non-superadmin admins are always scoped to their own workspace.
    # If no client_id was specified, default to their active workspace.
    # If one was specified, verify they actually belong to it.
    if current_user.role != "superadmin":
        if client_id is None:
            # Force scope to the requesting user's active client from the JWT.
            client_id = token_data.active_client_id
        else:
            # MT-2: verify the admin belongs to the requested client.
            access_check = await db.execute(
                select(UserClient).where(
                    UserClient.user_id == current_user.id,
                    UserClient.client_id == client_id,
                )
            )
            if access_check.scalar_one_or_none() is None:
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


@router.get("/provider-usage")
async def get_provider_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    token_data: TokenData = Depends(get_token_data),
    provider: str | None = Query(None, description="Filter by provider name (e.g. 'apollo')"),
    start: datetime | None = Query(None, description="Start of date range (ISO 8601, UTC)"),
    end: datetime | None = Query(None, description="End of date range (ISO 8601, UTC)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """Return provider API usage logs for the calling admin's client.

    Superadmins see all clients unless a specific client_id is embedded in their JWT.
    Results are ordered newest-first.

    Apollo credit notes: Apollo does not expose per-call credit deductions in API
    responses. credits_used will always be null; credits_estimated is computed from
    operation type (lead_enrich=1, company_enrich=1, contact_pull=reveal_count).
    """
    from fastapi import HTTPException

    # Scope to the admin's active client (superadmins see their own client unless acting globally)
    scoped_client_id = token_data.active_client_id
    if current_user.role != "superadmin":
        # Non-superadmin: always scope to their active client from the JWT
        if scoped_client_id is None:
            raise HTTPException(status_code=403, detail="No active client in token")

    filters = []
    if scoped_client_id is not None:
        filters.append(ProviderUsageLog.client_id == scoped_client_id)
    if provider:
        filters.append(ProviderUsageLog.provider == provider)
    if start:
        filters.append(ProviderUsageLog.created_at >= start)
    if end:
        filters.append(ProviderUsageLog.created_at <= end)

    total = (
        await db.execute(
            select(func.count()).select_from(ProviderUsageLog).where(*filters)
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            select(ProviderUsageLog)
            .where(*filters)
            .order_by(ProviderUsageLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()

    # Aggregation summary over the same window
    agg = (
        await db.execute(
            select(
                func.sum(ProviderUsageLog.request_count).label("total_requests"),
                func.sum(ProviderUsageLog.records_returned).label("total_records"),
                func.sum(ProviderUsageLog.credits_estimated).label("total_credits_estimated"),
            )
            .where(*filters)
        )
    ).one()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "summary": {
            "total_requests": agg.total_requests or 0,
            "total_records_returned": agg.total_records or 0,
            "total_credits_estimated": agg.total_credits_estimated or 0,
            "credits_used_note": (
                "Apollo does not return per-call credit usage. "
                "credits_used is always null; use credits_estimated instead."
            ),
        },
        "items": [
            {
                "id": row.id,
                "client_id": row.client_id,
                "provider": row.provider,
                "operation": row.operation,
                "entity_id": row.entity_id,
                "request_count": row.request_count,
                "records_returned": row.records_returned,
                "credits_used": row.credits_used,
                "credits_estimated": row.credits_estimated,
                "extra": row.extra,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }
