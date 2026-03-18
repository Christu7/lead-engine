import asyncio
import json
import logging
import signal

from app.core.config import settings
from app.core.database import async_session
from app.core.logging_config import configure_logging
from app.core.redis import redis
from app.models.lead import Lead
from app.services.ai_enrichment import run_analysis_for_lead
from app.services.enrichment import DEFAULT_PROVIDERS, EnrichmentPipeline
from app.services.enrichment.queue import QUEUE_KEY

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger("worker")

shutdown = asyncio.Event()


def _handle_signal() -> None:
    logger.info("Shutdown signal received")
    shutdown.set()


async def process_task(payload: dict) -> None:
    lead_id = payload["lead_id"]
    client_id = payload["client_id"]
    logger.info(
        "Processing enrichment for lead %d (client %d)",
        lead_id,
        client_id,
        extra={"lead_id": lead_id, "client_id": client_id},
    )

    pipeline = EnrichmentPipeline(DEFAULT_PROVIDERS)

    async with async_session() as db:
        try:
            await pipeline.run(db, lead_id, client_id)
            logger.info(
                "Enrichment complete for lead %d",
                lead_id,
                extra={"lead_id": lead_id, "client_id": client_id},
            )
        except Exception:
            logger.exception(
                "Enrichment failed for lead %d",
                lead_id,
                extra={"lead_id": lead_id, "client_id": client_id},
            )
            lead = await db.get(Lead, lead_id)
            if lead and lead.enrichment_status != "failed":
                lead.enrichment_status = "failed"
                await db.commit()
            return  # Do not proceed to AI analysis if enrichment failed

    # Trigger AI analysis as the final step after successful enrichment.
    # Uses its own DB session; failures are logged and dead-lettered but do
    # not retroactively mark enrichment as failed.
    try:
        await run_analysis_for_lead(lead_id, client_id)
    except Exception:
        logger.exception(
            "Unexpected error in AI analysis for lead %d",
            lead_id,
            extra={"lead_id": lead_id, "client_id": client_id},
        )


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    logger.info("Worker started, waiting for tasks on '%s'", QUEUE_KEY)

    while not shutdown.is_set():
        result = await redis.brpop(QUEUE_KEY, timeout=1)
        if result is None:
            continue

        _, raw = result
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Invalid payload: %s", raw)
            continue

        await process_task(payload)

    logger.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(main())
