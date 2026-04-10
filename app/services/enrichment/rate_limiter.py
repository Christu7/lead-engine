import logging
import time
import uuid

from app.core.redis import redis

logger = logging.getLogger(__name__)

# Default rate limits: (max_requests, window_seconds)
DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "apollo": (5, 60),
    "clearbit": (10, 60),
    "proxycurl": (10, 60),
}

# Atomic sliding-window rate limiter.
#
# All three operations execute as a single Redis command:
#   1. Prune entries older than window_start (ZREMRANGEBYSCORE)
#   2. Count entries remaining in the window (ZCARD)
#   3. Conditionally insert this request (ZADD + EXPIRE)
#
# Because Redis is single-threaded and Lua scripts run without interleaving,
# no two concurrent callers can observe the same count and both decide to
# insert — the second caller's ZCARD will see the entry the first one wrote.
#
# KEYS[1]  – sorted-set key for this (provider, client_id) pair
# ARGV[1]  – window_start: upper bound for pruning (entries with score ≤ this are stale)
# ARGV[2]  – now: current Unix timestamp (float as string), used as the ZADD score
# ARGV[3]  – max_requests: integer admission limit
# ARGV[4]  – window: TTL in seconds applied to the key after each successful insert
# ARGV[5]  – request_id: unique member name (UUID hex) so concurrent inserts at
#             the same timestamp never collide on the sorted-set member name
#
# Returns 1 if the request is admitted, 0 if rate-limited.
_ACQUIRE_LUA = """
local key       = KEYS[1]
local win_start = ARGV[1]
local now       = ARGV[2]
local max_req   = tonumber(ARGV[3])
local win_ttl   = tonumber(ARGV[4])
local req_id    = ARGV[5]

redis.call('ZREMRANGEBYSCORE', key, '-inf', win_start)
local count = redis.call('ZCARD', key)
if count < max_req then
    redis.call('ZADD', key, now, req_id)
    redis.call('EXPIRE', key, win_ttl)
    return 1
end
return 0
"""


async def acquire(provider_name: str, client_id: int) -> bool:
    """Atomic sliding-window rate limiter using a Redis Lua script.

    Returns True if the request is allowed, False if rate-limited.
    On Redis failure, allows the request (fail-open) to avoid blocking enrichment.
    """
    max_requests, window = DEFAULT_LIMITS.get(provider_name, (10, 60))
    key = f"ratelimit:{provider_name}:{client_id}"
    now = time.time()
    window_start = now - window
    request_id = uuid.uuid4().hex

    try:
        result = await redis.eval(
            _ACQUIRE_LUA,
            1,
            key,
            str(window_start),
            str(now),
            str(max_requests),
            str(window),
            request_id,
        )
        return bool(result)
    except Exception as exc:
        logger.warning(
            "Rate limiter Redis error for %s client %d — allowing request: %s",
            provider_name,
            client_id,
            exc,
        )
        return True
