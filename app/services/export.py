"""Export service: CSV generation and webhook dispatch for leads."""
import csv
import io
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.schemas.export import (
    DEFAULT_EXPORT_FIELDS,
    FIELD_LABELS,
    ExportRequest,
    LeadFilters,
)

logger = logging.getLogger(__name__)

EXPORT_CAP = 10_000


# ---------------------------------------------------------------------------
# Filter query builder (mirrors list_leads in lead.py)
# ---------------------------------------------------------------------------

def _build_filter_query(client_id: int, filters: LeadFilters):
    """Return a SELECT query for Lead with all export filters applied."""
    query = select(Lead).where(Lead.client_id == client_id)

    if filters.source is not None:
        query = query.where(Lead.source == filters.source)
    if filters.status is not None:
        query = query.where(Lead.status == filters.status)
    if filters.score_min is not None:
        query = query.where(Lead.score >= filters.score_min)
    if filters.score_max is not None:
        query = query.where(Lead.score <= filters.score_max)
    if filters.search is not None:
        pattern = f"%{filters.search}%"
        query = query.where(
            or_(
                Lead.name.ilike(pattern),
                Lead.email.ilike(pattern),
                Lead.company.ilike(pattern),
            )
        )
    if filters.date_from is not None:
        query = query.where(Lead.created_at >= filters.date_from)
    if filters.date_to is not None:
        query = query.where(Lead.created_at <= filters.date_to)

    return query


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _get_from_enrichment(enrichment_data: dict | None, *keys: str) -> str:
    """Search all provider sub-dicts for the first non-None value at any of keys."""
    if not enrichment_data:
        return ""
    for provider_data in enrichment_data.values():
        if not isinstance(provider_data, dict):
            continue
        for key in keys:
            val = provider_data.get(key)
            if val is not None:
                return str(val)
    return ""


def _get_location(enrichment_data: dict | None) -> str:
    if not enrichment_data:
        return ""
    for provider_data in enrichment_data.values():
        if not isinstance(provider_data, dict):
            continue
        parts = [
            provider_data.get("city"),
            provider_data.get("state"),
            provider_data.get("country"),
        ]
        parts = [str(p) for p in parts if p]
        if parts:
            return ", ".join(parts)
    return ""


def _extract_field(lead: Lead, field: str) -> str:
    """Return the string value for a single export field on a lead."""
    ed = lead.enrichment_data or {}
    ai = lead.ai_analysis or {}

    match field:
        case "name":
            return lead.name or ""
        case "email":
            return lead.email or ""
        case "phone":
            return lead.phone or ""
        case "company":
            return lead.company or ""
        case "title":
            return lead.title or ""
        case "source":
            return lead.source or ""
        case "status":
            return lead.status or ""
        case "score":
            return "" if lead.score is None else str(lead.score)
        case "enrichment_status":
            return lead.enrichment_status or ""
        case "apollo_id":
            return lead.apollo_id or ""
        case "linkedin_url":
            return _get_from_enrichment(ed, "linkedin_url")
        case "industry":
            return _get_from_enrichment(ed, "company_industry", "industry")
        case "employee_count":
            return _get_from_enrichment(ed, "employee_count")
        case "location":
            return _get_location(ed)
        case "ai_qualification":
            qual = ai.get("qualification") or {}
            return qual.get("rating", "") if isinstance(qual, dict) else ""
        case "ai_icebreakers":
            icebreakers = ai.get("icebreakers") or []
            return " | ".join(str(i) for i in icebreakers) if isinstance(icebreakers, list) else ""
        case "ai_email_angle":
            val = ai.get("email_angle")
            return str(val) if val is not None else ""
        case "created_at":
            return _format_dt(lead.created_at)
        case "enriched_at":
            # Lead model has no dedicated enriched_at column; use ai_analyzed_at as proxy.
            return _format_dt(lead.ai_analyzed_at)
        case _:
            return ""


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

async def count_export_leads(
    db: AsyncSession, client_id: int, filters: LeadFilters
) -> int:
    """Return count of leads matching filters, capped at EXPORT_CAP."""
    base = _build_filter_query(client_id, filters)
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()
    return min(int(total), EXPORT_CAP)


async def generate_csv(
    db: AsyncSession, client_id: int, request: ExportRequest
) -> tuple[str, int]:
    """Fetch filtered leads and build CSV text. Returns (csv_text, row_count)."""
    fields = request.fields or list(DEFAULT_EXPORT_FIELDS)

    query = (
        _build_filter_query(client_id, request.filters)
        .order_by(Lead.created_at.desc())
        .limit(EXPORT_CAP)
    )
    result = await db.execute(query)
    leads = list(result.scalars().all())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([FIELD_LABELS.get(f, f) for f in fields])
    for lead in leads:
        writer.writerow([_extract_field(lead, f) for f in fields])

    return buf.getvalue(), len(leads)


# ---------------------------------------------------------------------------
# Webhook export (background task)
# ---------------------------------------------------------------------------

def _lead_to_dict(
    lead: Lead,
    include_enrichment: bool = True,
    include_ai: bool = False,
) -> dict[str, Any]:
    """Serialize a Lead to a dict for a webhook payload."""
    data: dict[str, Any] = {
        "id": lead.id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "company": lead.company,
        "title": lead.title,
        "source": lead.source,
        "status": lead.status,
        "score": lead.score,
        "apollo_id": lead.apollo_id,
        "enrichment_status": lead.enrichment_status,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }
    if include_enrichment:
        data["enrichment_data"] = lead.enrichment_data
    if include_ai:
        data["ai_analysis"] = lead.ai_analysis
        data["ai_analyzed_at"] = (
            lead.ai_analyzed_at.isoformat() if lead.ai_analyzed_at else None
        )
    return data


async def _post_batch(
    client: httpx.AsyncClient,
    webhook_url: str,
    batch: list[dict],
    batch_num: int,
    total_batches: int,
    export_id: str,
    client_id: int,
) -> bool:
    """POST a single batch. Returns True on success, False on any failure."""
    payload = {
        "batch": batch_num,
        "total_batches": total_batches,
        "leads": batch,
        "export_id": export_id,
        "client_id": str(client_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = await client.post(webhook_url, json=payload, timeout=30)
        if resp.status_code >= 400:
            logger.error(
                "Webhook export batch %d/%d failed with HTTP %d",
                batch_num,
                total_batches,
                resp.status_code,
                extra={
                    "export_id": export_id,
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "status_code": resp.status_code,
                },
            )
            return False
        return True
    except Exception as exc:
        logger.error(
            "Webhook export batch %d/%d error: %s",
            batch_num,
            total_batches,
            exc,
            extra={"export_id": export_id, "batch_num": batch_num},
        )
        return False


async def dispatch_webhook_export(
    webhook_url: str,
    client_id: int,
    filters: LeadFilters,
    batch_size: int,
    include_enrichment: bool,
    include_ai_analysis: bool,
    export_id: str,
) -> None:
    """Background task: fetch leads then POST them in batches to webhook_url."""
    from app.core.database import async_session

    async with async_session() as db:
        query = (
            _build_filter_query(client_id, filters)
            .order_by(Lead.created_at.desc())
            .limit(EXPORT_CAP)
        )
        result = await db.execute(query)
        leads = list(result.scalars().all())

    lead_dicts = [
        _lead_to_dict(lead, include_enrichment, include_ai_analysis) for lead in leads
    ]
    total = len(lead_dicts)
    total_batches = max(1, math.ceil(total / batch_size))
    failed_batches = 0

    async with httpx.AsyncClient() as client:
        for i in range(total_batches):
            batch = lead_dicts[i * batch_size : (i + 1) * batch_size]
            ok = await _post_batch(
                client, webhook_url, batch, i + 1, total_batches, export_id, client_id
            )
            if not ok:
                failed_batches += 1

    logger.info(
        "Webhook export %s complete: %d leads, %d/%d batches succeeded",
        export_id,
        total,
        total_batches - failed_batches,
        total_batches,
        extra={"export_id": export_id, "client_id": client_id},
    )

    if total_batches > 0 and failed_batches > total_batches / 2:
        # > 50% batches failed — record in dead letter for manual review.
        # Using DeadLetterType.ROUTING (closest match; no EXPORT type exists).
        try:
            from app.core.redis import redis
            from app.services.dead_letter import DeadLetterService, DeadLetterType

            dl_svc = DeadLetterService(redis)
            await dl_svc.push(
                DeadLetterType.ROUTING,
                lead_id=0,  # no single lead — export-level failure
                client_id=client_id,
                error=(
                    f"Webhook export {export_id}: {failed_batches}/{total_batches} "
                    f"batches failed to {webhook_url}"
                ),
                extra={"export_id": export_id, "webhook_url": webhook_url},
            )
        except Exception as dl_exc:
            logger.error(
                "Failed to write dead letter for webhook export %s: %s",
                export_id,
                dl_exc,
            )
