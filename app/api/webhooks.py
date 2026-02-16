from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_api_key_auth, get_client_id
from app.schemas.lead import LeadCreate, LeadResponse
from app.schemas.webhook import TypeformWebhookPayload, WebsiteWebhookPayload
from app.services import lead as lead_service
from app.services import webhook as webhook_service

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(get_api_key_auth)],
)


@router.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead_webhook(
    data: LeadCreate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.create_lead(db, data, client_id)
    return lead


@router.post("/typeform", response_model=LeadResponse, status_code=201)
async def typeform_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    raw_payload = await request.json()
    log = await webhook_service.log_webhook(db, "typeform", raw_payload)

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
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    raw_payload = await request.json()
    log = await webhook_service.log_webhook(db, "website", raw_payload)

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
