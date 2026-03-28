"""Enrichment queue helpers.

Delegates to the unified task_queue sorted-set implementation.
The QUEUE_KEY constant is kept for backward compatibility (admin dead-letter
retry code and the legacy list migration reference it).
"""
from app.services import task_queue as _tq

QUEUE_KEY = "enrichment_queue"
DELAY_QUEUE_KEY = "enrichment_queue:delayed"

MAX_RATE_LIMIT_RETRIES = 3
RATE_LIMIT_DELAY_SECONDS = 60


async def enqueue_enrichment(lead_id: int, client_id: int, retry_count: int = 0) -> None:
    """Enqueue a lead enrichment task for immediate processing."""
    await _tq.enqueue(
        "lead_enrichment",
        {"lead_id": lead_id, "client_id": client_id, "retry_count": retry_count},
    )


async def enqueue_enrichment_delayed(
    lead_id: int,
    client_id: int,
    retry_count: int,
    delay_seconds: int = RATE_LIMIT_DELAY_SECONDS,
) -> None:
    """Schedule a lead enrichment task to run after `delay_seconds` seconds."""
    await _tq.enqueue(
        "lead_enrichment",
        {"lead_id": lead_id, "client_id": client_id, "retry_count": retry_count},
        delay_seconds=delay_seconds,
    )


async def flush_delayed_queue() -> int:
    """No-op: the sorted-set task_queue handles scheduling natively.

    Kept for backward compatibility with imports that call this function.
    """
    return 0
