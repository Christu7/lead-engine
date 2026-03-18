import hashlib
import hmac
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_client_id_from_api_key
from app.schemas.lead import LeadCreate, LeadResponse
from app.schemas.webhook import ApolloWebhookPayload, TypeformWebhookPayload, WebsiteWebhookPayload
from app.services import lead as lead_service
from app.services import webhook as webhook_service


def _verify_apollo_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/apollo", response_model=LeadResponse, status_code=200)
async def apollo_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    if settings.APOLLO_WEBHOOK_SECRET:
        signature = request.headers.get("x-apollo-signature-256", "")
        if not signature or not _verify_apollo_signature(body, signature, settings.APOLLO_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid Apollo webhook signature")

    raw_payload = json.loads(body)
    log = await webhook_service.log_webhook(db, "apollo", raw_payload, client_id)

    try:
        payload = ApolloWebhookPayload(**raw_payload)
        lead_data = webhook_service.parse_apollo_payload(payload)
    except (ValueError, Exception) as exc:
        await webhook_service.mark_log_failed(db, log, str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    lead, _ = await lead_service.upsert_lead(db, lead_data, client_id)
    await webhook_service.mark_log_processed(db, log, lead.id)
    background_tasks.add_task(webhook_service.run_enrichment_background, lead.id, client_id)
    return lead


@router.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead_webhook(
    data: LeadCreate,
    client_id: int = Depends(get_client_id_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.create_lead(db, data, client_id)
    return lead


@router.post("/typeform", response_model=LeadResponse, status_code=201)
async def typeform_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    raw_payload = await request.json()
    log = await webhook_service.log_webhook(db, "typeform", raw_payload, client_id)

    try:
        payload = TypeformWebhookPayload(**raw_payload)
        lead_data = webhook_service.parse_typeform_payload(payload)
    except (ValueError, Exception) as exc:
        await webhook_service.mark_log_failed(db, log, str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    lead = await lead_service.create_lead(db, lead_data, client_id)
    await webhook_service.mark_log_processed(db, log, lead.id)
    background_tasks.add_task(webhook_service.run_enrichment_background, lead.id, client_id)
    return lead


@router.post("/website", response_model=LeadResponse, status_code=201)
async def website_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    raw_payload = await request.json()
    log = await webhook_service.log_webhook(db, "website", raw_payload, client_id)

    try:
        payload = WebsiteWebhookPayload(**raw_payload)
        lead_data = webhook_service.parse_website_payload(payload)
    except (ValueError, Exception) as exc:
        await webhook_service.mark_log_failed(db, log, str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    lead = await lead_service.create_lead(db, lead_data, client_id)
    await webhook_service.mark_log_processed(db, log, lead.id)
    background_tasks.add_task(webhook_service.run_enrichment_background, lead.id, client_id)
    return lead
