import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_log import WebhookLog
from app.schemas.lead import LeadCreate
from app.schemas.webhook import ApolloWebhookPayload, TypeformWebhookPayload, WebsiteWebhookPayload

logger = logging.getLogger(__name__)

# Typeform field ref → LeadCreate field mapping
TYPEFORM_REF_MAP = {
    "name": "name",
    "email": "email",
    "company": "company",
    "phone": "phone",
}


async def log_webhook(db: AsyncSession, source: str, raw_payload: dict, client_id: int) -> WebhookLog:
    """Create a webhook log entry. Commits immediately so the record survives downstream failures."""
    log = WebhookLog(source=source, raw_payload=raw_payload, status="received", client_id=client_id)
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def mark_log_processed(db: AsyncSession, log: WebhookLog, lead_id: int) -> None:
    log.status = "processed"
    log.lead_id = lead_id
    await db.commit()


async def mark_log_failed(db: AsyncSession, log: WebhookLog, error: str) -> None:
    log.status = "failed"
    log.error = error
    await db.commit()


def parse_typeform_payload(payload: TypeformWebhookPayload) -> LeadCreate:
    """Extract lead fields from Typeform answers. Raises ValueError if name or email missing."""
    fields: dict[str, str | None] = {}

    for answer in payload.form_response.answers:
        ref = answer.field.ref
        if ref not in TYPEFORM_REF_MAP:
            continue

        # Typeform stores value in a type-specific field
        value = answer.text or answer.email or answer.phone_number
        if value:
            fields[TYPEFORM_REF_MAP[ref]] = value

    if "name" not in fields or "email" not in fields:
        raise ValueError("Typeform payload missing required fields: name and email")

    return LeadCreate(
        name=fields["name"],
        email=fields["email"],
        phone=fields.get("phone"),
        company=fields.get("company"),
        source="typeform",
    )


def parse_website_payload(payload: WebsiteWebhookPayload) -> LeadCreate:
    """Map flat website form fields to LeadCreate."""
    return LeadCreate(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        title=payload.title,
        source="website",
    )


def parse_apollo_payload(payload: ApolloWebhookPayload) -> LeadCreate:
    """Map Apollo webhook contact fields to LeadCreate. Raises ValueError if email is missing."""
    contact = payload.contact
    if not contact.email:
        raise ValueError("Apollo payload missing required field: email")

    name = contact.name or ""
    if not name:
        first = contact.first_name or ""
        last = contact.last_name or ""
        name = f"{first} {last}".strip()
    if not name:
        name = contact.email.split("@")[0]

    phone = None
    for ph in contact.phone_numbers:
        raw = (ph.raw_number or ph.sanitized_number or "").strip()
        if raw:
            phone = raw
            break

    enrichment: dict = {}
    if contact.linkedin_url:
        enrichment["linkedin_url"] = contact.linkedin_url

    return LeadCreate(
        name=name,
        email=contact.email,
        phone=phone,
        company=contact.organization_name,
        title=contact.title,
        apollo_id=contact.id,
        source="apollo",
        enrichment_data=enrichment or None,
    )
