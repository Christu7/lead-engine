import time

from app.core.redis import redis

# Default rate limits: (max_requests, window_seconds)
DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "apollo": (5, 60),
    "clearbit": (10, 60),
    "proxycurl": (10, 60),
}


async def acquire(provider_name: str, client_id: int) -> bool:
    """Sliding-window rate limiter using Redis sorted sets.

    Returns True if the request is allowed, False if rate-limited.
    """
    max_requests, window = DEFAULT_LIMITS.get(provider_name, (10, 60))
    key = f"ratelimit:{provider_name}:{client_id}"
    now = time.time()
    window_start = now - window

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zcard(key)
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, window)
    results = await pipe.execute()

    current_count = results[1]
    return current_count < max_requests
