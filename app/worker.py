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

# Tasks moved here atomically via RPOPLPUSH; removed after completion
IN_PROGRESS_KEY = f"{QUEUE_KEY}:processing"


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


async def recover_stranded_tasks() -> None:
    """On startup, requeue any tasks that were in-progress when the worker crashed.

    Tasks moved to IN_PROGRESS_KEY via RPOPLPUSH but never removed (because the
    worker crashed) are recovered here by pushing them back onto QUEUE_KEY.
    """
    stranded: list[bytes] = []
    while True:
        item = await redis.rpoplpush(IN_PROGRESS_KEY, QUEUE_KEY)
        if item is None:
            break
        stranded.append(item)

    if stranded:
        logger.warning(
            "Recovered %d stranded task(s) from previous worker crash",
            len(stranded),
            extra={"count": len(stranded)},
        )


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    await recover_stranded_tasks()

    logger.info("Worker started, waiting for tasks on '%s'", QUEUE_KEY)

    while not shutdown.is_set():
        # Atomically move from queue to in-progress list so a crash doesn't lose the task
        raw = await redis.brpoplpush(QUEUE_KEY, IN_PROGRESS_KEY, timeout=1)
        if raw is None:
            continue

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Invalid payload: %s", raw)
            # Remove the invalid item from in-progress
            await redis.lrem(IN_PROGRESS_KEY, 1, raw)
            continue

        try:
            await process_task(payload)
        finally:
            # Remove from in-progress regardless of success or failure
            await redis.lrem(IN_PROGRESS_KEY, 1, raw)

    logger.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(main())
