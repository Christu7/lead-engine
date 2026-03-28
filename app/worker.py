import asyncio
import logging
import signal
import uuid

from app.core.config import settings
from app.core.database import async_session
from app.core.logging_config import configure_logging
from app.core.redis import redis
from app.models.lead import Lead
from app.services.ai_enrichment import run_analysis_for_lead
from app.services.enrichment import DEFAULT_PROVIDERS, EnrichmentPipeline
from app.services import task_queue
from app.services.task_queue import (
    MAX_TASK_RETRIES,
    RATE_LIMIT_DELAYS,
    TRANSIENT_DELAYS,
)

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger("worker")

shutdown = asyncio.Event()


def _handle_signal() -> None:
    logger.info("Shutdown signal received")
    shutdown.set()


# ---------------------------------------------------------------------------
# Lead enrichment task
# ---------------------------------------------------------------------------


async def process_lead_task(payload: dict) -> None:
    """Run the full lead enrichment pipeline for a single lead."""
    lead_id = payload["lead_id"]
    client_id = payload["client_id"]
    retry_count: int = payload.get("retry_count", 0)
    logger.info(
        "Processing lead enrichment for lead %d (client %d, retry %d)",
        lead_id,
        client_id,
        retry_count,
        extra={"lead_id": lead_id, "client_id": client_id, "retry_count": retry_count},
    )

    pipeline = EnrichmentPipeline(DEFAULT_PROVIDERS)

    async with async_session() as db:
        try:
            await pipeline.run(db, lead_id, client_id, retry_count=retry_count)
            logger.info(
                "Lead enrichment complete for lead %d",
                lead_id,
                extra={"lead_id": lead_id, "client_id": client_id},
            )
        except Exception:
            logger.exception(
                "Lead enrichment failed for lead %d",
                lead_id,
                extra={"lead_id": lead_id, "client_id": client_id},
            )
            lead = await db.get(Lead, lead_id)
            if lead and lead.enrichment_status != "failed":
                lead.enrichment_status = "failed"
                await db.commit()
            return

    # AI analysis runs after successful enrichment; failures are isolated.
    try:
        await run_analysis_for_lead(lead_id, client_id)
    except Exception:
        logger.exception(
            "Unexpected error in AI analysis for lead %d",
            lead_id,
            extra={"lead_id": lead_id, "client_id": client_id},
        )


# ---------------------------------------------------------------------------
# Company enrichment task
# ---------------------------------------------------------------------------


async def process_company_task(raw: str, payload: dict) -> None:
    """Run Apollo org enrichment for a single company, with tiered retry."""
    from app.core.exceptions import EnrichmentProviderError
    from app.services.apollo_company import ApolloCompanyEnrichmentService
    from app.services.company import get_company as _get_company
    from app.services.dead_letter import DeadLetterService, DeadLetterType

    company_id_str: str = payload.get("company_id", "")
    client_id: int = payload.get("client_id", 0)
    retry_count: int = payload.get("retry_count", 0)

    if not company_id_str or not client_id:
        logger.error(
            "company_enrichment: invalid payload — missing company_id or client_id",
            extra={"payload": payload},
        )
        await task_queue.ack(raw)
        return

    try:
        company_id = uuid.UUID(company_id_str)
    except ValueError:
        logger.error(
            "company_enrichment: malformed company_id '%s'",
            company_id_str,
        )
        await task_queue.ack(raw)
        return

    try:
        async with async_session() as db:
            company = await _get_company(db, company_id, client_id)
            if company is None:
                logger.error(
                    "company_enrichment: company %s not found or wrong client",
                    company_id_str,
                    extra={"company_id": company_id_str, "client_id": client_id},
                )
                await task_queue.ack(raw)
                return
            svc = ApolloCompanyEnrichmentService()
            await svc.enrich_company(db, company, client_id)

        await task_queue.ack(raw)
        logger.info(
            "company_enrichment: complete for %s",
            company_id_str,
            extra={"company_id": company_id_str, "client_id": client_id},
        )

    except EnrichmentProviderError as exc:
        reason_lower = str(exc).lower()
        is_rate_limited = "429" in reason_lower or "rate" in reason_lower

        if retry_count >= MAX_TASK_RETRIES:
            logger.error(
                "company_enrichment: exhausted %d retries for %s — dead lettering",
                MAX_TASK_RETRIES,
                company_id_str,
                extra={"company_id": company_id_str, "client_id": client_id},
            )
            try:
                dl_svc = DeadLetterService(redis)
                await dl_svc.push(
                    DeadLetterType.ENRICHMENT,
                    lead_id=0,
                    client_id=client_id,
                    error=f"Company {company_id_str}: {exc}",
                )
            except Exception as dl_exc:
                logger.error("company_enrichment: failed to write dead letter: %s", dl_exc)
            await task_queue.ack(raw)
            return

        if is_rate_limited:
            delay = RATE_LIMIT_DELAYS[min(retry_count, len(RATE_LIMIT_DELAYS) - 1)]
            logger.warning(
                "company_enrichment: rate-limited for %s (retry %d) — requeueing in %ds",
                company_id_str,
                retry_count,
                delay,
                extra={"company_id": company_id_str, "client_id": client_id},
            )
            await task_queue.nack_rate_limited(raw, delay, retry_count + 1)
        else:
            delay = TRANSIENT_DELAYS[min(retry_count, len(TRANSIENT_DELAYS) - 1)]
            logger.warning(
                "company_enrichment: transient error for %s (retry %d) — requeueing in %ds: %s",
                company_id_str,
                retry_count,
                delay,
                exc,
                extra={"company_id": company_id_str, "client_id": client_id},
            )
            await task_queue.nack_transient(raw, delay, retry_count + 1)

    except Exception:
        logger.exception(
            "company_enrichment: unexpected error for %s",
            company_id_str,
            extra={"company_id": company_id_str, "client_id": client_id},
        )
        await task_queue.ack(raw)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    # Recover tasks stranded in processing set from a previous crash
    stranded = await task_queue.recover_stranded()
    if stranded:
        logger.warning(
            "Recovered %d stranded task(s) from previous worker crash",
            stranded,
            extra={"count": stranded},
        )

    # Migrate any leftover items from the old list-based enrichment_queue
    migrated = await task_queue.migrate_legacy_list_queue()
    if migrated:
        logger.info(
            "Migrated %d task(s) from legacy enrichment_queue to task_queue",
            migrated,
            extra={"count": migrated},
        )

    logger.info("Worker started, polling task_queue")

    inter_task_delay = settings.APOLLO_REQUEST_DELAY_MS / 1000.0

    while not shutdown.is_set():
        result = await task_queue.dequeue()

        if result is None:
            # No task ready — short sleep to avoid busy-wait
            await asyncio.sleep(0.1)
            continue

        raw, task_data = result
        task_type: str = task_data.get("task_type", "")
        payload: dict = task_data.get("payload", {})

        if task_type == "lead_enrichment":
            await process_lead_task(payload)
            # For lead tasks the pipeline manages its own ack via enqueue_enrichment_delayed.
            # We must ack the task_queue entry ourselves after the pipeline returns.
            await task_queue.ack(raw)
            await asyncio.sleep(inter_task_delay)

        elif task_type == "company_enrichment":
            await process_company_task(raw, payload)
            # ack/nack is handled inside process_company_task
            await asyncio.sleep(inter_task_delay)

        else:
            logger.error(
                "Unknown task_type '%s' — discarding",
                task_type,
                extra={"task_type": task_type, "payload": payload},
            )
            await task_queue.ack(raw)

    logger.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(main())
