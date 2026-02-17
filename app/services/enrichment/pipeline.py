import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.lead import EnrichmentLog, Lead
from app.services.enrichment import rate_limiter
from app.services.enrichment.base import EnrichmentProvider, EnrichmentResult
from app.services.enrichment.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

# API key names in client.settings["enrichment"]
API_KEY_MAP = {
    "apollo": "apollo_api_key",
    "clearbit": "clearbit_api_key",
    "proxycurl": "proxycurl_api_key",
}


def _cache_key_for_provider(name: str, lead: Lead) -> str | None:
    """Return the cache lookup key for a provider, or None if not available."""
    if name == "proxycurl":
        return (lead.enrichment_data or {}).get("apollo", {}).get("linkedin_url")
    return lead.email


class EnrichmentPipeline:
    def __init__(self, providers: list[EnrichmentProvider]) -> None:
        self.providers = providers

    async def run(self, db: AsyncSession, lead_id: int, client_id: int) -> None:
        lead = await db.get(Lead, lead_id)
        if not lead:
            logger.warning("Enrichment: lead %d not found", lead_id)
            return

        client = await db.get(Client, client_id)
        if not client:
            logger.warning("Enrichment: client %d not found", client_id)
            return

        lead.enrichment_status = "enriching"
        await db.commit()

        enrichment_keys = (client.settings or {}).get("enrichment", {})

        try:
            for provider in self.providers:
                name = provider.provider_name
                key_field = API_KEY_MAP.get(name)

                # Skip if no API key configured for this provider
                api_key = enrichment_keys.get(key_field) if key_field else None
                if not api_key:
                    logger.debug("Enrichment: skipping %s — no API key for client %d", name, client_id)
                    continue

                # Skip if provider says enrichment not needed
                if not provider.should_enrich(lead):
                    logger.debug("Enrichment: skipping %s — not needed for lead %d", name, lead_id)
                    continue

                # Check cache
                cache_key = _cache_key_for_provider(name, lead)
                cached = await get_cached(name, cache_key) if cache_key else None

                if cached is not None:
                    logger.info("Enrichment: cache hit for %s lead %d", name, lead_id)
                    result = EnrichmentResult(
                        provider_name=name,
                        success=True,
                        data=cached,
                        raw_response=cached,
                    )
                else:
                    # Rate limit check
                    if not await rate_limiter.acquire(name, client_id):
                        logger.info("Enrichment: rate-limited %s for client %d", name, client_id)
                        db.add(EnrichmentLog(
                            lead_id=lead_id,
                            client_id=client_id,
                            provider=name,
                            success=False,
                            raw_response={"error": "rate_limited"},
                        ))
                        continue

                    # Call provider
                    result = await provider.enrich(lead, api_key)

                    # Cache successful results
                    if result.success and result.data and cache_key:
                        await set_cached(name, cache_key, result.data)

                # Log result
                db.add(EnrichmentLog(
                    lead_id=lead_id,
                    client_id=client_id,
                    provider=name,
                    success=result.success,
                    raw_response=result.raw_response,
                ))

                if result.success and result.data:
                    # Merge into enrichment_data under provider namespace
                    old = lead.enrichment_data or {}
                    lead.enrichment_data = {**old, name: result.data}

                    # Promote fields to lead if currently empty
                    if not lead.company and result.data.get("company_name"):
                        lead.company = result.data["company_name"]
                    if not lead.title and result.data.get("title"):
                        lead.title = result.data["title"]
                elif not result.success:
                    logger.warning("Enrichment: %s failed for lead %d: %s", name, lead_id, result.error)

            lead.enrichment_status = "enriched"
        except Exception:
            lead.enrichment_status = "failed"
            raise
        finally:
            await db.commit()
