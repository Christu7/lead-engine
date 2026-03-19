from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import EnrichmentLog, Lead, RoutingLog
from app.schemas.dashboard import (
    ActivityItem,
    DashboardStatsResponse,
    LeadsBySource,
    ScoreBucket,
)
from app.schemas.routing import DestinationStats


async def get_dashboard_stats(
    db: AsyncSession, client_id: int
) -> DashboardStatsResponse:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Total leads
    total_q = select(func.count()).select_from(Lead).where(Lead.client_id == client_id)
    total_leads = (await db.execute(total_q)).scalar() or 0

    # Leads this week
    week_q = total_q.where(Lead.created_at >= week_ago)
    leads_this_week = (await db.execute(week_q)).scalar() or 0

    # Leads this month
    month_q = (
        select(func.count())
        .select_from(Lead)
        .where(Lead.client_id == client_id, Lead.created_at >= month_ago)
    )
    leads_this_month = (await db.execute(month_q)).scalar() or 0

    # Average score
    avg_q = (
        select(func.avg(Lead.score))
        .where(Lead.client_id == client_id, Lead.score.isnot(None))
    )
    avg_score_raw = (await db.execute(avg_q)).scalar()
    average_score = round(float(avg_score_raw), 1) if avg_score_raw is not None else None

    # Enrichment success rate
    enrich_total_q = (
        select(func.count())
        .select_from(EnrichmentLog)
        .where(EnrichmentLog.client_id == client_id)
    )
    enrich_success_q = (
        select(func.count())
        .select_from(EnrichmentLog)
        .where(EnrichmentLog.client_id == client_id, EnrichmentLog.success.is_(True))
    )
    enrich_total = (await db.execute(enrich_total_q)).scalar() or 0
    enrich_success = (await db.execute(enrich_success_q)).scalar() or 0
    enrichment_success_rate = (
        round(enrich_success / enrich_total * 100, 1) if enrich_total > 0 else 0.0
    )

    # Leads by source
    source_q = (
        select(Lead.source, func.count().label("count"))
        .where(Lead.client_id == client_id)
        .group_by(Lead.source)
    )
    source_rows = (await db.execute(source_q)).all()
    leads_by_source = [
        LeadsBySource(source=row.source or "unknown", count=row.count)
        for row in source_rows
    ]

    # Score distribution (5 buckets)
    buckets = [
        ("0–20", 0, 20),
        ("21–40", 21, 40),
        ("41–60", 41, 60),
        ("61–80", 61, 80),
        ("81–100", 81, 100),
    ]
    score_dist_q = select(
        *[
            func.count()
            .filter(Lead.score.between(lo, hi))
            .label(label)
            for label, lo, hi in buckets
        ]
    ).where(Lead.client_id == client_id, Lead.score.isnot(None))
    score_row = (await db.execute(score_dist_q)).one()
    score_distribution = [
        ScoreBucket(label=label, count=score_row._mapping[label])
        for label, _, _ in buckets
    ]

    # Routing breakdown by destination
    route_q = (
        select(
            RoutingLog.destination,
            func.count().label("total"),
            func.count().filter(RoutingLog.success.is_(True)).label("success"),
        )
        .where(RoutingLog.client_id == client_id)
        .group_by(RoutingLog.destination)
    )
    route_rows = (await db.execute(route_q)).all()
    routing_breakdown = [
        DestinationStats(
            destination=row.destination,
            total=row.total,
            success=row.success,
            failed=row.total - row.success,
        )
        for row in route_rows
    ]

    # Recent activity: last 5 leads, last 5 enrichment logs, last 5 routing logs
    activity: list[ActivityItem] = []

    # Recent leads
    recent_leads_q = (
        select(Lead.id, Lead.name, Lead.created_at)
        .where(Lead.client_id == client_id)
        .order_by(Lead.created_at.desc())
        .limit(5)
    )
    for row in (await db.execute(recent_leads_q)).all():
        activity.append(
            ActivityItem(
                type="lead",
                lead_id=row.id,
                lead_name=row.name,
                description="New lead created",
                timestamp=row.created_at.isoformat(),
            )
        )

    # Recent enrichment logs
    recent_enrich_q = (
        select(EnrichmentLog.lead_id, EnrichmentLog.provider, EnrichmentLog.success, EnrichmentLog.created_at, Lead.name)
        .join(Lead, EnrichmentLog.lead_id == Lead.id)
        .where(EnrichmentLog.client_id == client_id)
        .order_by(EnrichmentLog.created_at.desc())
        .limit(5)
    )
    for row in (await db.execute(recent_enrich_q)).all():
        status = "succeeded" if row.success else "failed"
        activity.append(
            ActivityItem(
                type="enrichment",
                lead_id=row.lead_id,
                lead_name=row.name,
                description=f"Enrichment via {row.provider} {status}",
                timestamp=row.created_at.isoformat(),
            )
        )

    # Recent routing logs
    recent_route_q = (
        select(RoutingLog.lead_id, RoutingLog.destination, RoutingLog.success, RoutingLog.created_at, Lead.name)
        .join(Lead, RoutingLog.lead_id == Lead.id)
        .where(RoutingLog.client_id == client_id)
        .order_by(RoutingLog.created_at.desc())
        .limit(5)
    )
    for row in (await db.execute(recent_route_q)).all():
        status = "success" if row.success else "failed"
        activity.append(
            ActivityItem(
                type="routing",
                lead_id=row.lead_id,
                lead_name=row.name,
                description=f"Routed to {row.destination} ({status})",
                timestamp=row.created_at.isoformat(),
            )
        )

    # Sort by timestamp desc, take 10
    activity.sort(key=lambda a: a.timestamp, reverse=True)
    recent_activity = activity[:10]

    return DashboardStatsResponse(
        total_leads=total_leads,
        leads_this_week=leads_this_week,
        leads_this_month=leads_this_month,
        enrichment_success_rate=enrichment_success_rate,
        average_score=average_score,
        leads_by_source=leads_by_source,
        score_distribution=score_distribution,
        routing_breakdown=routing_breakdown,
        recent_activity=recent_activity,
    )
