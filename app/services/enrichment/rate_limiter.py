import logging
import time

from app.core.redis import redis

logger = logging.getLogger(__name__)

# Default rate limits: (max_requests, window_seconds)
DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "apollo": (5, 60),
    "clearbit": (10, 60),
    "proxycurl": (10, 60),
}


async def acquire(provider_name: str, client_id: int) -> bool:
    """Sliding-window rate limiter using Redis sorted sets.

    Returns True if the request is allowed, False if rate-limited.
    On Redis failure, allows the request (fail-open) to avoid blocking enrichment.
    """
    max_requests, window = DEFAULT_LIMITS.get(provider_name, (10, 60))
    key = f"ratelimit:{provider_name}:{client_id}"
    now = time.time()
    window_start = now - window

    try:
        # Check current count first — do NOT add yet
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        results = await pipe.execute()

        current_count = results[1]
        if current_count >= max_requests:
            return False

        # Under the limit — record this request
        pipe = redis.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window)
        await pipe.execute()
        return True
    except Exception as exc:
        logger.warning(
            "Rate limiter Redis error for %s client %d — allowing request: %s",
            provider_name,
            client_id,
            exc,
        )
        return True
