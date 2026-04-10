"""Provider usage tracking — call record_provider_usage() after any external API call.

This module is intentionally thin: record_provider_usage() performs a db.add() only
(no commit, no async I/O) so it adds negligible latency to the critical path.
The row is flushed by the caller's existing db.commit().

Apollo credit notes
-------------------
Apollo does NOT expose credits_used in any people/match, organizations/enrich,
or mixed_people/api_search response. There is a separate /api/v1/account endpoint
that returns plan limits, but it does not give per-call deductions.

We therefore always set credits_used=None and populate credits_estimated based on
known Apollo pricing rules (as of 2024):
  - lead_enrich   (people/match):         1 credit per call
  - company_enrich (organizations/enrich): 1 credit per call
  - contact_pull  (reveal calls only):     1 credit per _reveal_ (people/match
                                           with reveal_personal_emails=True);
                                           the api_search itself does not deduct
                                           export credits unless the result is
                                           exported via the /people/bulk endpoint.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_usage_log import ProviderUsageLog

logger = logging.getLogger(__name__)

# Estimated credits per operation type (Apollo-specific; update if pricing changes)
_APOLLO_CREDIT_ESTIMATES: dict[str, int] = {
    "lead_enrich": 1,       # one people/match call
    "company_enrich": 1,    # one organizations/enrich call
    # contact_pull is variable; caller passes credits_estimated directly
}


def record_provider_usage(
    db: AsyncSession,
    *,
    client_id: int,
    provider: str,
    operation: str,
    entity_id: str | None = None,
    request_count: int = 1,
    records_returned: int = 0,
    credits_used: int | None = None,
    credits_estimated: int | None = None,
    extra: dict | None = None,
) -> None:
    """Queue a ProviderUsageLog row for insertion.

    This is synchronous and does NOT commit — the caller's db.commit() will flush it.
    Never raises; logs a warning on unexpected errors instead of crashing the caller.
    """
    try:
        # Auto-estimate credits for known Apollo operations if not explicitly provided
        if credits_estimated is None and provider == "apollo":
            credits_estimated = _APOLLO_CREDIT_ESTIMATES.get(operation)

        db.add(
            ProviderUsageLog(
                client_id=client_id,
                provider=provider,
                operation=operation,
                entity_id=entity_id,
                request_count=request_count,
                records_returned=records_returned,
                credits_used=credits_used,
                credits_estimated=credits_estimated,
                extra=extra,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "record_provider_usage: failed to queue usage log",
            extra={
                "provider": provider,
                "operation": operation,
                "client_id": client_id,
                "error": str(exc),
            },
        )
