"""Integration-style unit tests: contact pull filters × usage tracking consistency.

Verifies that ProviderUsageLog.extra accurately reflects the relationship between
what Apollo returned and what survived the client-side exclude_keywords post-filter.

All HTTP and DB calls are mocked — no network or database needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.provider_usage_log import ProviderUsageLog
from app.schemas.company import ContactPullFilters


def _make_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _make_company():
    c = MagicMock()
    c.id = "company-uuid"
    c.apollo_id = "apollo-org-1"
    c.name = "Acme"
    return c


def _make_person(title: str, email: str, idx: int = 0) -> dict:
    return {
        "id": f"person-{idx}",
        "first_name": "A",
        "last_name": "B",
        "email": email,
        "title": title,
        "organization": {},
        "linkedin_url": None,
    }


async def _fake_upsert(db, lead_data, client_id):
    lead = MagicMock()
    lead.company_id = "company-uuid"  # already set → no extra commit in loop
    return lead, "created"


def _get_usage_row(db) -> ProviderUsageLog | None:
    return next(
        (c[0][0] for c in db.add.call_args_list if type(c[0][0]).__name__ == "ProviderUsageLog"),
        None,
    )


# ── Core consistency checks ───────────────────────────────────────────────────

@pytest.mark.unit
class TestFilterUsageConsistency:

    @pytest.mark.asyncio
    async def test_returned_from_provider_reflects_pre_filter_count(self):
        """records_returned must equal what Apollo sent, not what survived the filter."""
        people = [
            _make_person("Software Engineer", "eng@x.com", 0),
            _make_person("Marketing Intern", "intern@x.com", 1),
            _make_person("Product Manager", "pm@x.com", 2),
        ]
        # 1 of 3 will be filtered out by exclude_keywords=["intern"]
        filters = ContactPullFilters(exclude_keywords=["intern"], limit=10)

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 3}}
            return resp

        db = _make_db()
        company = _make_company()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=_fake_upsert), \
             patch("httpx.AsyncClient") as cls:
            http = AsyncMock()
            http.post = fake_post
            cls.return_value.__aenter__ = AsyncMock(return_value=http)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            await ApolloCompanyEnrichmentService().pull_contacts_from_company(
                db, company, client_id=1, filters=filters
            )

        row = _get_usage_row(db)
        assert row is not None
        # records_returned is the pre-filter count (what Apollo sent)
        assert row.records_returned == 3

    @pytest.mark.asyncio
    async def test_extra_filtered_out_count_matches_exclusions(self):
        """extra.filtered_out_count must equal the number removed by exclude_keywords."""
        people = [
            _make_person("Software Engineer", "eng@x.com", 0),
            _make_person("Marketing Intern", "intern@x.com", 1),
            _make_person("Sales Intern", "sales_intern@x.com", 2),
            _make_person("Director", "dir@x.com", 3),
        ]
        # 2 of 4 titles contain "intern"
        filters = ContactPullFilters(exclude_keywords=["intern"], limit=10)

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 4}}
            return resp

        db = _make_db()
        company = _make_company()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=_fake_upsert), \
             patch("httpx.AsyncClient") as cls:
            http = AsyncMock()
            http.post = fake_post
            cls.return_value.__aenter__ = AsyncMock(return_value=http)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            await ApolloCompanyEnrichmentService().pull_contacts_from_company(
                db, company, client_id=1, filters=filters
            )

        row = _get_usage_row(db)
        assert row is not None
        assert row.extra["filtered_out_count"] == 2
        assert row.extra["returned_from_provider"] == 4

    @pytest.mark.asyncio
    async def test_final_saved_count_equals_created_plus_updated(self):
        """extra.final_saved_count must equal created + updated leads."""
        people = [
            _make_person("VP of Sales", f"vp{i}@x.com", i)
            for i in range(5)
        ]
        filters = ContactPullFilters(limit=10)

        call_count = 0

        async def fake_upsert_alternating(db, lead_data, client_id):
            nonlocal call_count
            lead = MagicMock()
            lead.company_id = "company-uuid"
            action = "created" if call_count % 2 == 0 else "updated"
            call_count += 1
            return lead, action

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 5}}
            return resp

        db = _make_db()
        company = _make_company()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=fake_upsert_alternating), \
             patch("httpx.AsyncClient") as cls:
            http = AsyncMock()
            http.post = fake_post
            cls.return_value.__aenter__ = AsyncMock(return_value=http)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            result = await ApolloCompanyEnrichmentService().pull_contacts_from_company(
                db, company, client_id=1, filters=filters
            )

        row = _get_usage_row(db)
        assert row is not None
        # 5 calls: indices 0,2,4 → created (3); indices 1,3 → updated (2)
        assert result["created"] == 3
        assert result["updated"] == 2
        assert row.extra["final_saved_count"] == 5  # 3 + 2

    @pytest.mark.asyncio
    async def test_requested_count_reflects_filters_limit(self):
        """extra.requested_count must equal filters.limit, not the number returned."""
        people = [_make_person("CEO", "ceo@x.com", 0)]
        filters = ContactPullFilters(limit=50)  # requested 50, got 1

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 1}}
            return resp

        db = _make_db()
        company = _make_company()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=_fake_upsert), \
             patch("httpx.AsyncClient") as cls:
            http = AsyncMock()
            http.post = fake_post
            cls.return_value.__aenter__ = AsyncMock(return_value=http)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            await ApolloCompanyEnrichmentService().pull_contacts_from_company(
                db, company, client_id=1, filters=filters
            )

        row = _get_usage_row(db)
        assert row is not None
        assert row.extra["requested_count"] == 50

    @pytest.mark.asyncio
    async def test_no_exclusion_filtered_out_is_zero(self):
        """When no exclude_keywords are set, filtered_out_count must be 0."""
        people = [_make_person("Engineer", f"e{i}@x.com", i) for i in range(4)]
        filters = ContactPullFilters(limit=10)  # no exclusions

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 4}}
            return resp

        db = _make_db()
        company = _make_company()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=_fake_upsert), \
             patch("httpx.AsyncClient") as cls:
            http = AsyncMock()
            http.post = fake_post
            cls.return_value.__aenter__ = AsyncMock(return_value=http)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            await ApolloCompanyEnrichmentService().pull_contacts_from_company(
                db, company, client_id=1, filters=filters
            )

        row = _get_usage_row(db)
        assert row is not None
        assert row.extra["filtered_out_count"] == 0
        assert row.extra["returned_from_provider"] == row.records_returned == 4

    @pytest.mark.asyncio
    async def test_usage_log_committed_at_end_of_pull(self):
        """db.commit() must be called after record_provider_usage to persist the row."""
        filters = ContactPullFilters(limit=10)

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": [], "pagination": {"total_entries": 0}}
            return resp

        db = _make_db()
        company = _make_company()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("httpx.AsyncClient") as cls:
            http = AsyncMock()
            http.post = fake_post
            cls.return_value.__aenter__ = AsyncMock(return_value=http)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            await ApolloCompanyEnrichmentService().pull_contacts_from_company(
                db, company, client_id=1, filters=filters
            )

        db.commit.assert_called()


# ── Pipeline: no usage log for cache hits ─────────────────────────────────────

@pytest.mark.unit
class TestPipelineCacheHitNoUsageLog:

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_create_usage_log(self):
        """A cache hit serves enrichment without an API call — no credit is consumed."""
        from tests.factories import ClientFactory, LeadFactory
        from app.services.enrichment.base import EnrichmentResult
        from app.services.enrichment.pipeline import EnrichmentPipeline
        from app.core.exceptions import ConfigurationError
        from app.models.lead import Lead
        from app.models.client import Client

        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(id=1, settings={"enrichment": {"apollo_api_key": "key"}})

        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = lead
        db.execute = AsyncMock(return_value=mock_result)

        async def mock_get(model, pk):
            if model is Lead:
                return lead
            if model is Client:
                return client
            return None
        db.get = AsyncMock(side_effect=mock_get)

        provider = MagicMock()
        provider.provider_name = "apollo"
        provider.should_enrich.return_value = True
        provider.enrich = AsyncMock(return_value=EnrichmentResult(
            provider_name="apollo", success=True, data={"title": "VP"}, raw_response={},
        ))

        cached_data = {"title": "Cached CTO"}

        rl = MagicMock()
        rl.acquire = AsyncMock(return_value=True)

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=cached_data)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=50)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            patch("app.services.enrichment.pipeline.rate_limiter", rl),
            patch(
                "app.services.enrichment.pipeline.dynamic_config.get_key",
                AsyncMock(side_effect=ConfigurationError("no key")),
            ),
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        # provider.enrich should NOT have been called (cache hit)
        provider.enrich.assert_not_called()

        # No ProviderUsageLog should have been added — no API call was made
        added_types = [type(c[0][0]).__name__ for c in db.add.call_args_list]
        assert "ProviderUsageLog" not in added_types

    @pytest.mark.asyncio
    async def test_actual_api_call_creates_usage_log(self):
        """A real provider call (no cache) must create a ProviderUsageLog row."""
        from tests.factories import ClientFactory, LeadFactory
        from app.services.enrichment.base import EnrichmentResult
        from app.services.enrichment.pipeline import EnrichmentPipeline
        from app.core.exceptions import ConfigurationError
        from app.models.lead import Lead
        from app.models.client import Client

        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(id=1, settings={"enrichment": {"apollo_api_key": "key"}})

        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = lead
        db.execute = AsyncMock(return_value=mock_result)

        async def mock_get(model, pk):
            if model is Lead:
                return lead
            if model is Client:
                return client
            return None
        db.get = AsyncMock(side_effect=mock_get)

        provider = MagicMock()
        provider.provider_name = "apollo"
        provider.should_enrich.return_value = True
        provider.enrich = AsyncMock(return_value=EnrichmentResult(
            provider_name="apollo", success=True, data={"title": "VP"}, raw_response={},
        ))

        rl = MagicMock()
        rl.acquire = AsyncMock(return_value=True)

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=50)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            patch("app.services.enrichment.pipeline.rate_limiter", rl),
            patch(
                "app.services.enrichment.pipeline.dynamic_config.get_key",
                AsyncMock(side_effect=ConfigurationError("no key")),
            ),
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        added_types = [type(c[0][0]).__name__ for c in db.add.call_args_list]
        assert "ProviderUsageLog" in added_types


# ── Pipeline: HTTP 429 creates usage log ──────────────────────────────────────

@pytest.mark.unit
class TestPipelineRateLimitedUsageLog:

    @pytest.mark.asyncio
    async def test_http_429_creates_usage_log_with_zero_credits(self):
        """A 429 response means an API call was made; it must be logged."""
        from tests.factories import ClientFactory, LeadFactory
        from app.services.enrichment.base import EnrichmentResult
        from app.services.enrichment.pipeline import EnrichmentPipeline
        from app.core.exceptions import ConfigurationError
        from app.models.lead import Lead
        from app.models.client import Client

        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(id=1, settings={"enrichment": {"apollo_api_key": "key"}})

        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = lead
        db.execute = AsyncMock(return_value=mock_result)

        async def mock_get(model, pk):
            if model is Lead:
                return lead
            if model is Client:
                return client
            return None
        db.get = AsyncMock(side_effect=mock_get)

        provider = MagicMock()
        provider.provider_name = "apollo"
        provider.should_enrich.return_value = True
        provider.enrich = AsyncMock(return_value=EnrichmentResult(
            provider_name="apollo",
            success=False,
            data={},
            raw_response=None,
            error="Apollo API rate limit exceeded (HTTP 429)",
            rate_limited=True,
        ))

        rl = MagicMock()
        rl.acquire = AsyncMock(return_value=True)

        with (
            patch("app.services.enrichment.pipeline.get_cached", AsyncMock(return_value=None)),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=0)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            patch("app.services.enrichment.pipeline.rate_limiter", rl),
            patch(
                "app.services.enrichment.pipeline.dynamic_config.get_key",
                AsyncMock(side_effect=ConfigurationError("no key")),
            ),
            patch("app.services.enrichment.queue.enqueue_enrichment_delayed", AsyncMock()),
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        added_types = [type(c[0][0]).__name__ for c in db.add.call_args_list]
        assert "ProviderUsageLog" in added_types

        usage_row = next(
            c[0][0] for c in db.add.call_args_list
            if type(c[0][0]).__name__ == "ProviderUsageLog"
        )
        assert usage_row.records_returned == 0
        assert usage_row.credits_estimated == 0
        assert usage_row.extra["skipped_reason"] == "rate_limited_429"
