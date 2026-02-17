import json

from app.core.redis import redis

QUEUE_KEY = "enrichment_queue"


async def enqueue_enrichment(lead_id: int, client_id: int) -> None:
    payload = json.dumps({"lead_id": lead_id, "client_id": client_id})
    await redis.lpush(QUEUE_KEY, payload)
