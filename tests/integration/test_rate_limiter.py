"""Integration tests for the atomic sliding-window rate limiter.

These tests require a live Redis instance.

Atomicity guarantee under test
-------------------------------
The old implementation used two separate Redis pipelines:

    pipe1: ZREMRANGEBYSCORE + ZCARD   → round-trip 1
    # Python checks count < limit
    pipe2: ZADD + EXPIRE              → round-trip 2

With asyncio.gather, coroutine A suspends at round-trip 1, then B runs its
round-trip 1 before A runs round-trip 2.  Both see the same count, both decide
to admit, both run round-trip 2 — over-admission.

The Lua script collapses all three operations into a single EVAL call.
Redis is single-threaded and never interleaves Lua execution, so the second
caller's ZCARD will always see the entry the first caller wrote.

The concurrent test (test_concurrent_calls_never_exceed_limit) directly
verifies this property: it fires N > limit coroutines simultaneously and
asserts exactly `limit` are admitted.
"""
import asyncio

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from unittest.mock import patch

from app.core.config import settings
from app.core.redis import redis
from app.services.enrichment import rate_limiter

# Use a provider name that won't match any real provider key in DEFAULT_LIMITS,
# and high client IDs to avoid any collision with production or other test data.
_TEST_PROVIDER = "test_rl_provider"
_TEST_CLIENT_BASE = 90_000


@pytest_asyncio.fixture(autouse=True)
async def flush_ratelimit_keys():
    """Wipe all rate-limit keys used by this module before and after each test.

    Creates a fresh Redis client per invocation to avoid event-loop binding
    issues when pytest-asyncio creates a new loop for each test.
    """
    r = redis_asyncio.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        for pattern in [
            f"ratelimit:{_TEST_PROVIDER}:*",
            "ratelimit:test_rl_fallback:*",
        ]:
            keys = await r.keys(pattern)
            if keys:
                await r.delete(*keys)
        yield
        for pattern in [
            f"ratelimit:{_TEST_PROVIDER}:*",
            "ratelimit:test_rl_fallback:*",
        ]:
            keys = await r.keys(pattern)
            if keys:
                await r.delete(*keys)
    finally:
        await r.aclose()


@pytest.mark.integration
class TestAtomicRateLimiter:

    async def test_allows_up_to_limit_then_denies(self):
        """Sequential calls: first max_req succeed, subsequent ones are rejected."""
        max_req = 4
        client_id = _TEST_CLIENT_BASE + 1

        with patch.dict(rate_limiter.DEFAULT_LIMITS, {_TEST_PROVIDER: (max_req, 60)}):
            results = [
                await rate_limiter.acquire(_TEST_PROVIDER, client_id)
                for _ in range(max_req + 2)
            ]

        assert results[:max_req] == [True] * max_req, (
            f"Expected first {max_req} calls to be admitted"
        )
        assert results[max_req] is False, "Call at limit+1 must be rejected"
        assert results[max_req + 1] is False, "Call at limit+2 must be rejected"

    async def test_concurrent_calls_never_exceed_limit(self):
        """The core atomicity test.

        asyncio.gather fires all coroutines in the same event loop.  With the
        old two-pipeline approach, every coroutine reads the same count before
        any of them write, so all admit — over-admission.

        With the Lua script, each EVAL is serialised by Redis.  Exactly
        max_req coroutines return True; the rest return False.
        """
        max_req = 3
        concurrent = 20
        client_id = _TEST_CLIENT_BASE + 2

        with patch.dict(rate_limiter.DEFAULT_LIMITS, {_TEST_PROVIDER: (max_req, 60)}):
            results = await asyncio.gather(
                *[rate_limiter.acquire(_TEST_PROVIDER, client_id) for _ in range(concurrent)]
            )

        allowed = sum(1 for r in results if r)
        assert allowed == max_req, (
            f"Expected exactly {max_req} admitted out of {concurrent} concurrent calls, "
            f"got {allowed}.  "
            "This indicates a race condition — the Lua atomicity guarantee is broken."
        )

    async def test_window_expiry_resets_limit(self):
        """After window_seconds have elapsed, stale entries are pruned and the
        limit resets so new requests are admitted."""
        max_req = 2
        window_secs = 1
        client_id = _TEST_CLIENT_BASE + 3

        with patch.dict(rate_limiter.DEFAULT_LIMITS, {_TEST_PROVIDER: (max_req, window_secs)}):
            # Fill the window to the limit
            for _ in range(max_req):
                assert await rate_limiter.acquire(_TEST_PROVIDER, client_id) is True

            # Verify we're now at the limit
            assert await rate_limiter.acquire(_TEST_PROVIDER, client_id) is False

            # Wait for the window to expire
            await asyncio.sleep(window_secs + 0.1)

            # Entries are pruned on the next acquire — should be admitted again
            assert await rate_limiter.acquire(_TEST_PROVIDER, client_id) is True

    async def test_different_clients_have_independent_quotas(self):
        """Rate-limit keys are namespaced by (provider, client_id).
        Exhausting one client's quota must not affect another."""
        max_req = 2
        client_a = _TEST_CLIENT_BASE + 4
        client_b = _TEST_CLIENT_BASE + 5

        with patch.dict(rate_limiter.DEFAULT_LIMITS, {_TEST_PROVIDER: (max_req, 60)}):
            for _ in range(max_req):
                assert await rate_limiter.acquire(_TEST_PROVIDER, client_a) is True
            assert await rate_limiter.acquire(_TEST_PROVIDER, client_a) is False

            # client_b is unaffected — full quota available
            assert await rate_limiter.acquire(_TEST_PROVIDER, client_b) is True
            assert await rate_limiter.acquire(_TEST_PROVIDER, client_b) is True
            assert await rate_limiter.acquire(_TEST_PROVIDER, client_b) is False

    async def test_unknown_provider_falls_back_to_default_limit(self):
        """Providers absent from DEFAULT_LIMITS use the (10, 60) fallback."""
        fallback_provider = "test_rl_fallback"
        client_id = _TEST_CLIENT_BASE + 6

        # Default limit is 10 — first 10 should all pass
        results = [
            await rate_limiter.acquire(fallback_provider, client_id) for _ in range(10)
        ]
        assert all(results), "All 10 calls within the default limit must be admitted"
        assert await rate_limiter.acquire(fallback_provider, client_id) is False, (
            "Call 11 must be rejected by the default limit of 10"
        )

    async def test_unique_member_per_request_prevents_collision(self):
        """Two calls at the (practically) same timestamp must both be recorded
        separately — not overwrite each other in the sorted set."""
        max_req = 5
        client_id = _TEST_CLIENT_BASE + 7

        with patch.dict(rate_limiter.DEFAULT_LIMITS, {_TEST_PROVIDER: (max_req, 60)}):
            # Fire max_req calls rapidly in sequence
            for i in range(max_req):
                result = await rate_limiter.acquire(_TEST_PROVIDER, client_id)
                assert result is True, (
                    f"Call {i + 1} should be admitted — UUID collision may have "
                    "caused a previous entry to be overwritten"
                )

            # Verify the sorted set actually contains max_req distinct entries
            key = f"ratelimit:{_TEST_PROVIDER}:{client_id}"
            count = await redis.zcard(key)
            assert count == max_req, (
                f"Sorted set should have {max_req} entries, got {count}. "
                "UUID member uniqueness may be broken."
            )
