"""Unit tests for enrichment cache key isolation.

Verifies that cache keys include client_id so Client A's cached data
cannot be read by Client B.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.enrichment.cache import _cache_key, get_cached, set_cached


@pytest.mark.unit
class TestCacheKeyIsolation:

    def test_cache_key_includes_client_id(self):
        """Different client_ids must produce different cache keys."""
        key_a = _cache_key("apollo", 1, "user@example.com")
        key_b = _cache_key("apollo", 2, "user@example.com")
        assert key_a != key_b

    def test_cache_key_format(self):
        """Cache key must embed client_id between provider and lookup key."""
        key = _cache_key("apollo", 42, "user@example.com")
        assert key == "enrich_cache:42:apollo:user@example.com"

    async def test_get_cached_client_a_cannot_read_client_b_cache(self):
        """A cache entry written for client A must not be returned for client B."""
        stored: dict[str, str] = {}

        async def fake_set(redis_key: str, value: str, ex: int) -> None:
            stored[redis_key] = value

        async def fake_get(redis_key: str):
            return stored.get(redis_key)

        mock_redis = AsyncMock()
        mock_redis.set.side_effect = fake_set
        mock_redis.get.side_effect = fake_get

        with patch("app.services.enrichment.cache.redis", mock_redis):
            # Client 1 writes a cache entry
            await set_cached("apollo", 1, "user@example.com", {"title": "CEO"})

            # Client 2 reads with the same provider + lookup key — must be a cache miss
            result = await get_cached("apollo", 2, "user@example.com")

        assert result is None, (
            "Client 2 should not be able to read Client 1's cached enrichment data"
        )

    async def test_get_cached_same_client_returns_data(self):
        """A cache entry written for client A is readable by client A."""
        stored: dict[str, str] = {}

        async def fake_set(redis_key: str, value: str, ex: int) -> None:
            stored[redis_key] = value

        async def fake_get(redis_key: str):
            raw = stored.get(redis_key)
            return raw.encode() if raw else None

        mock_redis = AsyncMock()
        mock_redis.set.side_effect = fake_set
        mock_redis.get.side_effect = fake_get

        data = {"title": "CTO", "company_name": "Acme"}

        with patch("app.services.enrichment.cache.redis", mock_redis):
            await set_cached("apollo", 1, "user@example.com", data)
            result = await get_cached("apollo", 1, "user@example.com")

        assert result == data
