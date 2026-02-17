import asyncio
import json
import logging
import signal

from app.core.database import async_session
from app.core.redis import redis
from app.models.lead import Lead
from app.services.enrichment import DEFAULT_PROVIDERS, EnrichmentPipeline
from app.services.enrichment.queue import QUEUE_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worker")

shutdown = asyncio.Event()


def _handle_signal() -> None:
    logger.info("Shutdown signal received")
    shutdown.set()


async def process_task(payload: dict) -> None:
    lead_id = payload["lead_id"]
    client_id = payload["client_id"]
    logger.info("Processing enrichment for lead %d (client %d)", lead_id, client_id)

    pipeline = EnrichmentPipeline(DEFAULT_PROVIDERS)

    async with async_session() as db:
        try:
            await pipeline.run(db, lead_id, client_id)
            logger.info("Enrichment complete for lead %d", lead_id)
        except Exception:
            logger.exception("Enrichment failed for lead %d", lead_id)
            # Ensure status is set to failed
            lead = await db.get(Lead, lead_id)
            if lead and lead.enrichment_status != "failed":
                lead.enrichment_status = "failed"
                await db.commit()


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
