import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dynamic_config import dynamic_config
from app.core.exceptions import ConfigurationError
from app.models.client import Client
from app.models.lead import EnrichmentLog, Lead
from app.services.enrichment import rate_limiter
from app.services.enrichment.base import EnrichmentProvider, EnrichmentResult
from app.services.enrichment.cache import get_cached, set_cached
from app.services.provider_usage import record_provider_usage
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

    async def run(self, db: AsyncSession, lead_id: int, client_id: int, retry_count: int = 0) -> None:
        result = await db.execute(
            select(Lead).where(Lead.id == lead_id, Lead.client_id == client_id)
        )
        lead = result.scalar_one_or_none()
        if not lead:
            # Determine whether this is a genuine not-found or a cross-tenant injection.
            # Look up by PK only to detect mismatch — but never log the true owner's client_id.
            other = await db.get(Lead, lead_id)
            if other is not None:
                logger.error(
                    "SECURITY: Enrichment rejected for lead %d — "
                    "task client_id %d does not match lead owner. "
                    "Possible cross-tenant task injection.",
                    lead_id,
                    client_id,
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
                        error="SECURITY: Lead does not belong to this client — task rejected",
                    )
                except Exception as dl_exc:
                    logger.error(
                        "Enrichment: failed to write dead letter for security violation "
                        "on lead %d: %s",
                        lead_id,
                        dl_exc,
                    )
            else:
                logger.warning(
                    "Enrichment: lead %d not found",
                    lead_id,
                    extra={"lead_id": lead_id, "client_id": client_id},
                )
            return

        client = await db.get(Client, client_id)
        if not client:
            logger.warning("Enrichment: client %d not found", client_id)
            return

        lead.enrichment_status = "enriching"
        await db.commit()

        # Capture custom fields BEFORE any provider writes so we can always restore them.
        # A re-enrichment must never wipe user-defined custom field data.
        preserved_custom = (lead.enrichment_data or {}).get("custom_fields", {})

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

                    # Provider-level rate limiting (HTTP 429) — log at WARNING, no dead-letter,
                    # treat the same as our internal rate-limiter (deferred, not failed).
                    # An HTTP call WAS made (we received a 429), so log provider usage.
                    if result.rate_limited:
                        logger.warning(
                            "Enrichment: %s returned HTTP 429 for lead %d — deferring",
                            name,
                            lead_id,
                            extra={"lead_id": lead_id, "provider": name, "client_id": client_id},
                        )
                        providers_rate_limited += 1
                        db.add(EnrichmentLog(
                            lead_id=lead_id,
                            client_id=client_id,
                            provider=name,
                            success=False,
                            raw_response={"error": result.error},
                        ))
                        record_provider_usage(
                            db,
                            client_id=client_id,
                            provider=name,
                            operation="lead_enrich",
                            entity_id=str(lead_id),
                            records_returned=0,
                            # Credit may or may not have been consumed on a 429; we don't know.
                            credits_estimated=0,
                            extra={"skipped_reason": "rate_limited_429"},
                        )
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
                # Only log API usage when an actual provider call was made.
                # Cache hits do not consume provider credits and must not be counted.
                if cached is None:
                    record_provider_usage(
                        db,
                        client_id=client_id,
                        provider=name,
                        operation="lead_enrich",
                        entity_id=str(lead_id),
                        records_returned=1 if (result.success and result.data) else 0,
                    )

                providers_attempted += 1

                if result.success:
                    # 404 / no_data counts as success — person not found is not a failure
                    providers_succeeded += 1
                    if result.data:
                        # Merge into enrichment_data under provider namespace.
                        # Explicitly restore custom_fields so no provider can overwrite them.
                        old = lead.enrichment_data or {}
                        lead.enrichment_data = {
                            **old,
                            name: result.data,
                            "custom_fields": preserved_custom,
                        }

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
                # All providers were rate-limited — defer with a delay, up to MAX_RATE_LIMIT_RETRIES
                from app.services.enrichment.queue import (
                    MAX_RATE_LIMIT_RETRIES,
                    RATE_LIMIT_DELAY_SECONDS,
                    enqueue_enrichment_delayed,
                )

                if retry_count >= MAX_RATE_LIMIT_RETRIES:
                    # Exhausted retries — move to dead letter so admins can see it
                    lead.enrichment_status = "failed"
                    logger.error(
                        "Enrichment: lead %d rate-limited %d times — moving to dead letter",
                        lead_id,
                        retry_count,
                        extra={"lead_id": lead_id, "client_id": client_id, "retry_count": retry_count},
                    )
                    try:
                        from app.core.redis import redis
                        from app.services.dead_letter import DeadLetterService, DeadLetterType

                        dl_svc = DeadLetterService(redis)
                        await dl_svc.push(
                            DeadLetterType.ENRICHMENT,
                            lead_id=lead_id,
                            client_id=client_id,
                            error=f"All providers rate-limited after {retry_count} retries",
                        )
                    except Exception as dl_exc:
                        logger.error(
                            "Enrichment: failed to write dead letter for lead %d: %s",
                            lead_id,
                            dl_exc,
                        )
                else:
                    lead.enrichment_status = "deferred"
                    logger.warning(
                        "Enrichment: all providers rate-limited for lead %d "
                        "(retry %d/%d) — requeueing in %ds",
                        lead_id,
                        retry_count + 1,
                        MAX_RATE_LIMIT_RETRIES,
                        RATE_LIMIT_DELAY_SECONDS,
                        extra={
                            "lead_id": lead_id,
                            "client_id": client_id,
                            "retry_count": retry_count,
                        },
                    )
                    try:
                        await enqueue_enrichment_delayed(
                            lead_id, client_id, retry_count=retry_count + 1
                        )
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
            # Restore custom_fields even on unexpected failures
            if preserved_custom:
                data = lead.enrichment_data or {}
                if data.get("custom_fields") != preserved_custom:
                    lead.enrichment_data = {**data, "custom_fields": preserved_custom}
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
            try:
                await db.commit()
            except Exception as commit_exc:
                logger.critical(
                    "Enrichment pipeline: DB commit failed in finally block — "
                    "lead %d may be stuck in 'enriching' status: %s",
                    lead_id,
                    commit_exc,
                    extra={"lead_id": lead_id, "client_id": client_id},
                )

        # Auto-fill custom fields from enrichment results before scoring
        if lead.enrichment_data:
            try:
                from app.services.custom_fields import apply_enrichment_mappings
                await apply_enrichment_mappings(
                    db, lead, lead.enrichment_data, client_id, "lead"
                )
                await db.refresh(lead)
            except Exception as map_exc:
                logger.warning(
                    "Enrichment pipeline: apply_enrichment_mappings failed for lead %d: %s",
                    lead_id,
                    map_exc,
                    extra={"lead_id": lead_id, "client_id": client_id},
                )

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
        finally:
            await db.commit()
