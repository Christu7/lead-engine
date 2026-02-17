import asyncio
import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.lead import Lead, RoutingLog
from app.schemas.routing import DestinationStats, RoutingResult, RoutingStatsResponse

logger = logging.getLogger(__name__)


def _build_ghl_payload(lead: Lead) -> dict:
    parts = (lead.name or "").split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    return {
        "email": lead.email,
        "phone": lead.phone,
        "firstName": first_name,
        "lastName": last_name,
        "companyName": lead.company,
        "source": lead.source,
        "tags": [f"score:{lead.score}", f"status:{lead.status}"],
        "customField": {
            "lead_id": lead.id,
            "title": lead.title,
            "score": lead.score,
            "enrichment_status": lead.enrichment_status,
        },
    }


async def _post_with_retry(
    url: str, payload: dict, max_retries: int = 3
) -> tuple[int | None, str | None]:
    last_code: int | None = None
    last_error: str | None = None

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                last_code = resp.status_code
                if 200 <= resp.status_code < 300:
                    return resp.status_code, None
                last_error = resp.text
        except Exception as exc:
            last_error = str(exc)

        if attempt < max_retries - 1:
            await asyncio.sleep(2**attempt)

    return last_code, last_error


async def route_lead(
    db: AsyncSession, lead: Lead, client_id: int
) -> RoutingResult:
    client = await db.get(Client, client_id)
    routing_cfg = (client.settings or {}).get("routing", {}) if client else {}

    inbound_threshold = routing_cfg.get("score_inbound_threshold", 70)
    outbound_threshold = routing_cfg.get("score_outbound_threshold", 40)

    score = lead.score or 0

    if score >= inbound_threshold:
        destination = "ghl_inbound"
        webhook_url = routing_cfg.get("ghl_inbound_webhook_url")
    elif score >= outbound_threshold:
        destination = "ghl_outbound"
        webhook_url = routing_cfg.get("ghl_outbound_webhook_url")
    else:
        db.add(RoutingLog(
            client_id=client_id,
            lead_id=lead.id,
            destination="manual_review",
            payload=None,
            response_code=None,
            success=False,
            error=None,
        ))
        return RoutingResult(
            destination="manual_review",
            status="manual_review",
            score=score,
        )

    if not webhook_url:
        return RoutingResult(
            destination=destination,
            status="no_config",
            score=score,
        )

    payload = _build_ghl_payload(lead)
    response_code, error = await _post_with_retry(webhook_url, payload)
    success = error is None

    db.add(RoutingLog(
        client_id=client_id,
        lead_id=lead.id,
        destination=destination,
        payload=payload,
        response_code=response_code,
        success=success,
        error=error,
    ))

    return RoutingResult(
        destination=destination,
        status="routed" if success else "failed",
        response_code=response_code,
        score=score,
    )


async def get_routing_stats(
    db: AsyncSession, client_id: int
) -> RoutingStatsResponse:
    total_q = select(func.count()).select_from(RoutingLog).where(
        RoutingLog.client_id == client_id
    )
    success_q = select(func.count()).select_from(RoutingLog).where(
        RoutingLog.client_id == client_id, RoutingLog.success.is_(True)
    )
    total = (await db.execute(total_q)).scalar() or 0
    success = (await db.execute(success_q)).scalar() or 0
    failed = total - success
    success_rate = (success / total * 100) if total > 0 else 0.0

    by_dest_q = (
        select(
            RoutingLog.destination,
            func.count().label("total"),
            func.count().filter(RoutingLog.success.is_(True)).label("success"),
        )
        .where(RoutingLog.client_id == client_id)
        .group_by(RoutingLog.destination)
    )
    rows = (await db.execute(by_dest_q)).all()
    by_destination = [
        DestinationStats(
            destination=row.destination,
            total=row.total,
            success=row.success,
            failed=row.total - row.success,
        )
        for row in rows
    ]

    return RoutingStatsResponse(
        total=total,
        success=success,
        failed=failed,
        success_rate=round(success_rate, 2),
        by_destination=by_destination,
    )
