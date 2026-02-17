import json

from app.core.redis import redis

CACHE_TTL = 7 * 24 * 60 * 60  # 7 days


def _cache_key(provider_name: str, key: str) -> str:
    return f"enrich_cache:{provider_name}:{key}"


async def get_cached(provider_name: str, key: str) -> dict | None:
    raw = await redis.get(_cache_key(provider_name, key))
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached(provider_name: str, key: str, data: dict) -> None:
    await redis.set(_cache_key(provider_name, key), json.dumps(data), ex=CACHE_TTL)
