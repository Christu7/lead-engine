import json
import logging

from app.core.redis import redis

logger = logging.getLogger(__name__)

CACHE_TTL = 7 * 24 * 60 * 60  # 7 days


def _cache_key(provider_name: str, client_id: int, key: str) -> str:
    return f"enrich_cache:{client_id}:{provider_name}:{key}"


async def get_cached(provider_name: str, client_id: int, key: str) -> dict | None:
    try:
        raw = await redis.get(_cache_key(provider_name, client_id, key))
    except Exception as exc:
        logger.warning("Cache get failed for %s:%s — %s", provider_name, key, exc)
        return None
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached(provider_name: str, client_id: int, key: str, data: dict) -> None:
    try:
        await redis.set(_cache_key(provider_name, client_id, key), json.dumps(data), ex=CACHE_TTL)
    except Exception as exc:
        logger.warning("Cache set failed for %s:%s — %s", provider_name, key, exc)
