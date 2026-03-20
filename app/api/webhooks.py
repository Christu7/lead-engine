import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
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
    client_id: int = Depends(get_client_id_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # Signature verification is mandatory — no secret means the endpoint is misconfigured.
    # NOTE: APOLLO_WEBHOOK_SECRET is a single global value shared across all clients.
    # Apollo does not support per-webhook secrets, so any client whose API key reaches
    # this endpoint gets the same signature validation. A per-client secret would require
    # Apollo to support dynamic secrets or routing through separate webhook URLs.
    if not settings.APOLLO_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=500,
            detail="APOLLO_WEBHOOK_SECRET is not configured on this server",
        )
    signature = request.headers.get("x-apollo-signature-256", "")
    if not signature or not _verify_apollo_signature(body, signature, settings.APOLLO_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Apollo webhook signature")

    try:
        raw_payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON payload")

    log = await webhook_service.log_webhook(db, "apollo", raw_payload, client_id)

    try:
        payload = ApolloWebhookPayload(**raw_payload)
        lead_data = webhook_service.parse_apollo_payload(payload)
    except (ValueError, Exception) as exc:
        await webhook_service.mark_log_failed(db, log, str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    # upsert_lead calls enqueue_enrichment for new leads — no background task needed
    lead, _ = await lead_service.upsert_lead(db, lead_data, client_id)
    await webhook_service.mark_log_processed(db, log, lead.id)
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
    client_id: int = Depends(get_client_id_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # Optional HMAC signature verification — enabled when TYPEFORM_WEBHOOK_SECRET is set.
    # Typeform sends the signature in the X-Typeform-Signature header as "sha256=<hex>".
    if settings.TYPEFORM_WEBHOOK_SECRET:
        sig = request.headers.get("x-typeform-signature", "")
        if not sig or not _verify_apollo_signature(body, sig, settings.TYPEFORM_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid Typeform webhook signature")

    try:
        raw_payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON payload")

    log = await webhook_service.log_webhook(db, "typeform", raw_payload, client_id)

    try:
        payload = TypeformWebhookPayload(**raw_payload)
        lead_data = webhook_service.parse_typeform_payload(payload)
    except (ValueError, Exception) as exc:
        await webhook_service.mark_log_failed(db, log, str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    # create_lead calls enqueue_enrichment — no separate background task needed
    lead = await lead_service.create_lead(db, lead_data, client_id)
    await webhook_service.mark_log_processed(db, log, lead.id)
    return lead


@router.post("/website", response_model=LeadResponse, status_code=201)
async def website_webhook(
    request: Request,
    client_id: int = Depends(get_client_id_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # Optional HMAC signature verification — enabled when WEBSITE_WEBHOOK_SECRET is set.
    # Callers must include the signature in X-Webhook-Signature as "sha256=<hex>".
    if settings.WEBSITE_WEBHOOK_SECRET:
        sig = request.headers.get("x-webhook-signature", "")
        if not sig or not _verify_apollo_signature(body, sig, settings.WEBSITE_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        raw_payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON payload")

    log = await webhook_service.log_webhook(db, "website", raw_payload, client_id)

    try:
        payload = WebsiteWebhookPayload(**raw_payload)
        lead_data = webhook_service.parse_website_payload(payload)
    except (ValueError, Exception) as exc:
        await webhook_service.mark_log_failed(db, log, str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    # create_lead calls enqueue_enrichment — no separate background task needed
    lead = await lead_service.create_lead(db, lead_data, client_id)
    await webhook_service.mark_log_processed(db, log, lead.id)
    return lead
