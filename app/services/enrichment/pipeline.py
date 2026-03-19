import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dynamic_config import dynamic_config
from app.core.exceptions import ConfigurationError
from app.models.client import Client
from app.models.lead import EnrichmentLog, Lead
from app.services.enrichment import rate_limiter
from app.services.enrichment.base import EnrichmentProvider, EnrichmentResult
from app.services.enrichment.cache import get_cached, set_cached
from app.services.routing import route_lead
from app.services.scoring import score_lead

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

        providers_attempted = 0
        providers_succeeded = 0
        providers_rate_limited = 0

        try:
            for provider in self.providers:
                name = provider.provider_name
                key_field = API_KEY_MAP.get(name)

                # Resolve API key: dynamic_config (ApiKeyStore → env var) first,
                # then fall back to legacy client.settings["enrichment"] keys.
                api_key: str | None = None
                try:
                    api_key = await dynamic_config.get_key(db, name)
                except ConfigurationError:
                    pass

                if not api_key:
                    api_key = enrichment_keys.get(key_field) if key_field else None

                if not api_key:
                    logger.debug(
                        "Enrichment: skipping %s — no API key for client %d",
                        name,
                        client_id,
                    )
                    continue

                # Skip if provider says enrichment not needed
                if not provider.should_enrich(lead):
                    logger.debug(
                        "Enrichment: skipping %s — not needed for lead %d",
                        name,
                        lead_id,
                    )
                    continue

                # Check cache (keyed by client_id to prevent cross-tenant leakage)
                cache_key = _cache_key_for_provider(name, lead)
                cached = await get_cached(name, client_id, cache_key) if cache_key else None

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
                        logger.info(
                            "Enrichment: rate-limited %s for client %d", name, client_id
                        )
                        providers_rate_limited += 1
                        db.add(EnrichmentLog(
                            lead_id=lead_id,
                            client_id=client_id,
                            provider=name,
                            success=False,
                            raw_response={"error": "rate_limited"},
                        ))
                        continue

                    # Call provider — catch unexpected exceptions so one bad provider
                    # doesn't abort the entire pipeline
                    try:
                        result = await provider.enrich(lead, api_key)
                    except Exception as exc:
                        logger.warning(
                            "Enrichment: %s raised unexpectedly for lead %d: %s",
                            name,
                            lead_id,
                            exc,
                            extra={"lead_id": lead_id, "provider": name},
                        )
                        providers_attempted += 1
                        db.add(EnrichmentLog(
                            lead_id=lead_id,
                            client_id=client_id,
                            provider=name,
                            success=False,
                            raw_response={"error": str(exc)},
                        ))
                        continue

                    # Cache successful results (keyed by client_id)
                    if result.success and result.data and cache_key:
                        await set_cached(name, client_id, cache_key, result.data)

                # Log result
                db.add(EnrichmentLog(
                    lead_id=lead_id,
                    client_id=client_id,
                    provider=name,
                    success=result.success,
                    raw_response=result.raw_response,
                ))

                providers_attempted += 1

                if result.success:
                    # 404 / no_data counts as success — person not found is not a failure
                    providers_succeeded += 1
                    if result.data:
                        # Merge into enrichment_data under provider namespace
                        old = lead.enrichment_data or {}
                        lead.enrichment_data = {**old, name: result.data}

                        # Promote fields to lead if currently empty
                        if not lead.company and result.data.get("company_name"):
                            lead.company = result.data["company_name"]
                        if not lead.title and result.data.get("title"):
                            lead.title = result.data["title"]
                elif not result.success:
                    logger.warning(
                        "Enrichment: %s failed for lead %d: %s",
                        name,
                        lead_id,
                        result.error,
                    )

            # Determine final enrichment status
            if providers_attempted == 0 and providers_rate_limited > 0:
                # All providers were rate-limited — defer and requeue
                lead.enrichment_status = "deferred"
                logger.warning(
                    "Enrichment: all providers rate-limited for lead %d, requeueing",
                    lead_id,
                    extra={"lead_id": lead_id, "client_id": client_id},
                )
                try:
                    from app.services.enrichment.queue import enqueue_enrichment
                    await enqueue_enrichment(lead_id, client_id)
                except Exception as requeue_exc:
                    logger.error(
                        "Enrichment: failed to requeue deferred lead %d: %s",
                        lead_id,
                        requeue_exc,
                    )
            elif providers_attempted == 0 or providers_succeeded == providers_attempted:
                lead.enrichment_status = "enriched"
            elif providers_succeeded > 0:
                lead.enrichment_status = "partial"
            else:
                lead.enrichment_status = "failed"
                logger.error(
                    "Enrichment: all %d provider(s) failed for lead %d",
                    providers_attempted,
                    lead_id,
                    extra={"lead_id": lead_id, "client_id": client_id},
                )
                # Push to dead letter so admins can retry
                try:
                    from app.core.redis import redis
                    from app.services.dead_letter import DeadLetterService, DeadLetterType

                    dl_svc = DeadLetterService(redis)
                    await dl_svc.push(
                        DeadLetterType.ENRICHMENT,
                        lead_id=lead_id,
                        client_id=client_id,
                        error=f"All {providers_attempted} enrichment provider(s) failed",
                    )
                except Exception as dl_exc:
                    logger.error(
                        "Enrichment: failed to write dead letter for lead %d: %s",
                        lead_id,
                        dl_exc,
                    )

        except Exception as exc:
            lead.enrichment_status = "failed"
            logger.exception(
                "Enrichment: unexpected error for lead %d",
                lead_id,
                extra={"lead_id": lead_id, "client_id": client_id},
            )
            try:
                from app.core.redis import redis
                from app.services.dead_letter import DeadLetterService, DeadLetterType

                dl_svc = DeadLetterService(redis)
                await dl_svc.push(
                    DeadLetterType.ENRICHMENT,
                    lead_id=lead_id,
                    client_id=client_id,
                    error=f"Unexpected pipeline error: {exc}",
                )
            except Exception as dl_exc:
                logger.error(
                    "Enrichment: failed to write dead letter for lead %d: %s",
                    lead_id,
                    dl_exc,
                )
            raise
        finally:
            await db.commit()

        # Score and route — separate concern, isolated from enrichment errors
        try:
            await score_lead(db, lead, client_id)
            await route_lead(db, lead, client_id)
        except Exception as exc:
            logger.error(
                "Enrichment pipeline: scoring/routing failed for lead %d: %s",
                lead_id,
                exc,
                extra={"lead_id": lead_id, "client_id": client_id},
            )
            try:
                from app.core.redis import redis
                from app.services.dead_letter import DeadLetterService, DeadLetterType

                dl_svc = DeadLetterService(redis)
                await dl_svc.push(
                    DeadLetterType.ROUTING,
                    lead_id=lead_id,
                    client_id=client_id,
                    error=f"Scoring/routing failed after enrichment: {exc}",
                )
            except Exception as dl_exc:
                logger.error(
                    "Enrichment: failed to write dead letter for lead %d: %s",
                    lead_id,
                    dl_exc,
                )
