"""Unit tests for EnrichmentPipeline.

DB is mocked with AsyncMock. Provider HTTP calls are mocked directly on
the provider's enrich() method (not via respx) to keep these focused on
pipeline orchestration logic.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.client import Client
from app.models.lead import Lead
from app.services.enrichment.base import EnrichmentResult
from app.services.enrichment.pipeline import EnrichmentPipeline
from tests.factories import ClientFactory, LeadFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(lead: Lead, client: Client):
    """Return a minimal AsyncSession mock wired to return the given lead/client."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()

    async def mock_get(model, pk):
        if model is Lead:
            return lead
        if model is Client:
            return client
        return None

    db.get = AsyncMock(side_effect=mock_get)
    return db


def _make_provider(name: str, result: EnrichmentResult, should_enrich: bool = True):
    """Return a mock provider that always returns the given EnrichmentResult."""
    provider = MagicMock()
    provider.provider_name = name
    provider.should_enrich.return_value = should_enrich
    provider.enrich = AsyncMock(return_value=result)
    return provider


def _success_result(name: str) -> EnrichmentResult:
    return EnrichmentResult(
        provider_name=name,
        success=True,
        data={"title": "VP Engineering", "company_name": "Acme"},
        raw_response={},
    )


def _fail_result(name: str, error: str = "API error") -> EnrichmentResult:
    return EnrichmentResult(
        provider_name=name,
        success=False,
        error=error,
        raw_response=None,
    )


# Patches applied to all tests in this module
COMMON_PATCHES = {
    "app.services.enrichment.pipeline.get_cached": AsyncMock(return_value=None),
    "app.services.enrichment.pipeline.set_cached": AsyncMock(),
    "app.services.enrichment.pipeline.score_lead": AsyncMock(return_value=50),
    "app.services.enrichment.pipeline.route_lead": AsyncMock(),
}


def _patch_rate_limiter_ok():
    rl = MagicMock()
    rl.acquire = AsyncMock(return_value=True)
    return patch("app.services.enrichment.pipeline.rate_limiter", rl)


@pytest.mark.unit
class TestEnrichmentPipeline:

    async def test_single_provider_success_sets_enriched(self):
        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1, settings={"enrichment": {"apollo_api_key": "key"}}
        )
        db = _make_db(lead, client)
        provider = _make_provider("apollo", _success_result("apollo"))

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=50)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            _patch_rate_limiter_ok(),
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        assert lead.enrichment_status == "enriched"
        assert lead.enrichment_data is not None
        assert "apollo" in lead.enrichment_data

    async def test_one_fail_one_success_sets_partial(self):
        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1,
            settings={
                "enrichment": {
                    "apollo_api_key": "key",
                    "clearbit_api_key": "key2",
                }
            },
        )
        db = _make_db(lead, client)
        apollo = _make_provider("apollo", _fail_result("apollo"))
        clearbit = _make_provider("clearbit", _success_result("clearbit"))

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=30)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            _patch_rate_limiter_ok(),
        ):
            pipeline = EnrichmentPipeline([apollo, clearbit])
            await pipeline.run(db, 1, 1)

        assert lead.enrichment_status == "partial"

    async def test_all_providers_fail_sets_failed_and_dead_letter(self):
        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1, settings={"enrichment": {"apollo_api_key": "key"}}
        )
        db = _make_db(lead, client)
        provider = _make_provider("apollo", _fail_result("apollo"))

        mock_dl = AsyncMock()

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=0)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            _patch_rate_limiter_ok(),
            patch("app.services.dead_letter.DeadLetterService.push", mock_dl),
            patch("app.core.redis.redis"),  # prevent real redis connection
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        assert lead.enrichment_status == "failed"

    async def test_no_api_key_skips_provider(self):
        """Provider without a configured API key should be silently skipped."""
        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(id=1, settings={"enrichment": {}})
        db = _make_db(lead, client)
        provider = _make_provider("apollo", _success_result("apollo"))

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=0)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            _patch_rate_limiter_ok(),
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        provider.enrich.assert_not_called()
        # No providers attempted → treated as "enriched" (nothing to do)
        assert lead.enrichment_status == "enriched"

    async def test_cache_hit_skips_http_call(self):
        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1, settings={"enrichment": {"apollo_api_key": "key"}}
        )
        db = _make_db(lead, client)
        provider = _make_provider("apollo", _success_result("apollo"))

        cached_data = {"title": "CTO", "company_name": "Cached Co"}

        with (
            patch(
                "app.services.enrichment.pipeline.get_cached",
                AsyncMock(return_value=cached_data),
            ),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=50)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            _patch_rate_limiter_ok(),
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        # enrich() should NOT have been called — cache hit short-circuited it
        provider.enrich.assert_not_called()
        assert lead.enrichment_status == "enriched"
        assert lead.enrichment_data["apollo"] == cached_data

    async def test_rate_limited_skips_provider(self):
        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1, settings={"enrichment": {"apollo_api_key": "key"}}
        )
        db = _make_db(lead, client)
        provider = _make_provider("apollo", _success_result("apollo"))

        rl = MagicMock()
        rl.acquire = AsyncMock(return_value=False)  # rate-limited

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=0)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            patch("app.services.enrichment.pipeline.rate_limiter", rl),
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        provider.enrich.assert_not_called()
        # Rate-limited provider was not attempted — no status change from "enriched"
        assert lead.enrichment_status == "enriched"

    async def test_provider_exception_does_not_abort_pipeline(self):
        """An unexpected exception from a provider should be caught; pipeline continues."""
        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1,
            settings={
                "enrichment": {
                    "apollo_api_key": "key",
                    "clearbit_api_key": "key2",
                }
            },
        )
        db = _make_db(lead, client)
        apollo = _make_provider("apollo", _success_result("apollo"))
        apollo.enrich = AsyncMock(side_effect=RuntimeError("unexpected!"))
        clearbit = _make_provider("clearbit", _success_result("clearbit"))

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=40)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            _patch_rate_limiter_ok(),
        ):
            pipeline = EnrichmentPipeline([apollo, clearbit])
            await pipeline.run(db, 1, 1)

        # Apollo failed (exception), clearbit succeeded → partial
        assert lead.enrichment_status == "partial"

    async def test_lead_not_found_returns_early(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        db.commit = AsyncMock()

        pipeline = EnrichmentPipeline([])
        # Should not raise
        await pipeline.run(db, 999, 1)
        db.commit.assert_not_called()
