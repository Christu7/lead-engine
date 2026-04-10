"""Unit tests for provider usage tracking.

Covers:
- record_provider_usage() queues a row via db.add() without committing
- Correct client_id attribution
- credits_estimated auto-filled for known Apollo operations
- credits_estimated passed through explicitly (contact_pull)
- credits_used stays None for Apollo (never set by API response)
- Pipeline integration: usage log created after successful provider call
- Pipeline integration: usage log created after failed provider call (records_returned=0)
- enrich_company usage log
- pull_contacts_from_company usage log with reveal tracking
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from app.services.provider_usage import record_provider_usage
from app.models.provider_usage_log import ProviderUsageLog


# ── record_provider_usage helper ─────────────────────────────────────────────

@pytest.mark.unit
class TestRecordProviderUsage:

    def _make_db(self):
        db = MagicMock()
        db.add = MagicMock()
        return db

    def test_queues_db_add(self):
        db = self._make_db()
        record_provider_usage(db, client_id=1, provider="apollo", operation="lead_enrich")
        db.add.assert_called_once()
        row = db.add.call_args[0][0]
        assert isinstance(row, ProviderUsageLog)

    def test_correct_client_id(self):
        db = self._make_db()
        record_provider_usage(db, client_id=42, provider="apollo", operation="lead_enrich")
        row = db.add.call_args[0][0]
        assert row.client_id == 42

    def test_entity_id_stored(self):
        db = self._make_db()
        record_provider_usage(
            db, client_id=1, provider="apollo", operation="lead_enrich", entity_id="99"
        )
        row = db.add.call_args[0][0]
        assert row.entity_id == "99"

    def test_credits_used_is_none(self):
        """Apollo never returns credits_used — it must always be None."""
        db = self._make_db()
        record_provider_usage(db, client_id=1, provider="apollo", operation="lead_enrich")
        row = db.add.call_args[0][0]
        assert row.credits_used is None

    def test_lead_enrich_auto_estimates_1_credit(self):
        db = self._make_db()
        record_provider_usage(db, client_id=1, provider="apollo", operation="lead_enrich")
        row = db.add.call_args[0][0]
        assert row.credits_estimated == 1

    def test_company_enrich_auto_estimates_1_credit(self):
        db = self._make_db()
        record_provider_usage(db, client_id=1, provider="apollo", operation="company_enrich")
        row = db.add.call_args[0][0]
        assert row.credits_estimated == 1

    def test_contact_pull_explicit_credits_estimated(self):
        """contact_pull estimate depends on reveal count — caller must pass it."""
        db = self._make_db()
        record_provider_usage(
            db,
            client_id=1,
            provider="apollo",
            operation="contact_pull",
            credits_estimated=5,
        )
        row = db.add.call_args[0][0]
        assert row.credits_estimated == 5

    def test_contact_pull_zero_reveals_is_zero_credits(self):
        db = self._make_db()
        record_provider_usage(
            db,
            client_id=1,
            provider="apollo",
            operation="contact_pull",
            credits_estimated=0,
        )
        row = db.add.call_args[0][0]
        assert row.credits_estimated == 0

    def test_non_apollo_provider_no_auto_estimate(self):
        """Auto-estimate only applies to Apollo; other providers get None."""
        db = self._make_db()
        record_provider_usage(db, client_id=1, provider="clearbit", operation="lead_enrich")
        row = db.add.call_args[0][0]
        assert row.credits_estimated is None

    def test_explicit_credits_estimated_overrides_auto(self):
        db = self._make_db()
        record_provider_usage(
            db, client_id=1, provider="apollo", operation="lead_enrich", credits_estimated=99
        )
        row = db.add.call_args[0][0]
        assert row.credits_estimated == 99

    def test_records_returned_stored(self):
        db = self._make_db()
        record_provider_usage(
            db, client_id=1, provider="apollo", operation="contact_pull",
            records_returned=15, credits_estimated=3,
        )
        row = db.add.call_args[0][0]
        assert row.records_returned == 15

    def test_request_count_stored(self):
        db = self._make_db()
        record_provider_usage(
            db, client_id=1, provider="apollo", operation="contact_pull",
            request_count=4, credits_estimated=3,
        )
        row = db.add.call_args[0][0]
        assert row.request_count == 4

    def test_extra_stored(self):
        db = self._make_db()
        extra = {"reveal_attempts": 3, "reveals_succeeded": 2}
        record_provider_usage(
            db, client_id=1, provider="apollo", operation="contact_pull",
            credits_estimated=3, extra=extra,
        )
        row = db.add.call_args[0][0]
        assert row.extra == extra

    def test_does_not_commit(self):
        """record_provider_usage must NOT commit — the caller owns the transaction."""
        db = self._make_db()
        db.commit = MagicMock()
        record_provider_usage(db, client_id=1, provider="apollo", operation="lead_enrich")
        db.commit.assert_not_called()

    def test_never_raises_on_db_error(self):
        """Failures in record_provider_usage must not propagate to the caller."""
        db = MagicMock()
        db.add = MagicMock(side_effect=RuntimeError("DB exploded"))
        # Should not raise
        record_provider_usage(db, client_id=1, provider="apollo", operation="lead_enrich")


# ── Pipeline integration ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestPipelineUsageLogging:
    """Verify that EnrichmentPipeline calls record_provider_usage correctly."""

    def _make_db(self, lead, client):
        from app.models.lead import Lead
        from app.models.client import Client

        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        db.delete = MagicMock()

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
        return db

    @pytest.mark.asyncio
    async def test_usage_log_created_on_successful_enrich(self):
        from tests.factories import ClientFactory, LeadFactory
        from app.services.enrichment.base import EnrichmentResult
        from app.services.enrichment.pipeline import EnrichmentPipeline
        from app.core.exceptions import ConfigurationError

        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1, settings={"enrichment": {"apollo_api_key": "key"}}
        )
        db = self._make_db(lead, client)

        provider = MagicMock()
        provider.provider_name = "apollo"
        provider.should_enrich.return_value = True
        provider.enrich = AsyncMock(return_value=EnrichmentResult(
            provider_name="apollo", success=True,
            data={"title": "VP"}, raw_response={},
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

        # db.add should have been called for EnrichmentLog AND ProviderUsageLog
        added_types = [type(c[0][0]).__name__ for c in db.add.call_args_list]
        assert "ProviderUsageLog" in added_types

        usage_row = next(
            c[0][0] for c in db.add.call_args_list
            if type(c[0][0]).__name__ == "ProviderUsageLog"
        )
        assert usage_row.client_id == 1
        assert usage_row.provider == "apollo"
        assert usage_row.operation == "lead_enrich"
        assert usage_row.entity_id == "1"
        assert usage_row.records_returned == 1
        assert usage_row.credits_used is None
        assert usage_row.credits_estimated == 1

    @pytest.mark.asyncio
    async def test_usage_log_records_returned_zero_on_no_data(self):
        """no_data result (404) → records_returned should be 0."""
        from tests.factories import ClientFactory, LeadFactory
        from app.services.enrichment.base import EnrichmentResult
        from app.services.enrichment.pipeline import EnrichmentPipeline
        from app.core.exceptions import ConfigurationError

        lead = LeadFactory.build(id=1, client_id=1, email="a@b.com")
        client = ClientFactory.build(
            id=1, settings={"enrichment": {"apollo_api_key": "key"}}
        )
        db = self._make_db(lead, client)

        provider = MagicMock()
        provider.provider_name = "apollo"
        provider.should_enrich.return_value = True
        provider.enrich = AsyncMock(return_value=EnrichmentResult(
            provider_name="apollo", success=True,
            data={},  # no data (person not found)
            raw_response=None,
            no_data=True,
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
        ):
            pipeline = EnrichmentPipeline([provider])
            await pipeline.run(db, 1, 1)

        usage_row = next(
            (c[0][0] for c in db.add.call_args_list
             if type(c[0][0]).__name__ == "ProviderUsageLog"),
            None,
        )
        assert usage_row is not None
        assert usage_row.records_returned == 0

    @pytest.mark.asyncio
    async def test_usage_log_client_id_attribution(self):
        """Usage log must carry the correct client_id, not a hardcoded value."""
        from tests.factories import ClientFactory, LeadFactory
        from app.services.enrichment.base import EnrichmentResult
        from app.services.enrichment.pipeline import EnrichmentPipeline
        from app.core.exceptions import ConfigurationError

        lead = LeadFactory.build(id=5, client_id=99, email="x@y.com")
        client = ClientFactory.build(
            id=99, settings={"enrichment": {"apollo_api_key": "key"}}
        )
        db = self._make_db(lead, client)

        provider = MagicMock()
        provider.provider_name = "apollo"
        provider.should_enrich.return_value = True
        provider.enrich = AsyncMock(return_value=EnrichmentResult(
            provider_name="apollo", success=True, data={"title": "CTO"}, raw_response={},
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
            await pipeline.run(db, 5, 99)

        usage_row = next(
            c[0][0] for c in db.add.call_args_list
            if type(c[0][0]).__name__ == "ProviderUsageLog"
        )
        assert usage_row.client_id == 99


# ── contact_pull credits_estimated ────────────────────────────────────────────

@pytest.mark.unit
class TestContactPullCreditsEstimate:
    """Verify credits_estimated = reveal_attempts for contact_pull."""

    @pytest.mark.asyncio
    async def test_credits_estimated_equals_reveal_attempts(self):
        """Each reveal call to people/match costs 1 credit; the search itself is free."""
        people = [
            {"id": f"p{i}", "first_name": "A", "last_name": "B",
             "email": f"a{i}@x.com", "title": "VP", "organization": {}, "linkedin_url": None}
            for i in range(3)
        ]

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 3}}
            return resp

        company = MagicMock()
        company.id = "comp-uuid"
        company.apollo_id = "apollo-org-1"
        company.name = "Acme"

        async def fake_upsert(db, lead_data, client_id):
            lead = MagicMock()
            lead.company_id = company.id
            return lead, "created"

        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=fake_upsert), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            from app.schemas.company import ContactPullFilters
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(
                db, company, client_id=1,
                filters=ContactPullFilters(limit=10),
            )

        usage_row = next(
            (c[0][0] for c in db.add.call_args_list
             if type(c[0][0]).__name__ == "ProviderUsageLog"),
            None,
        )
        assert usage_row is not None
        assert usage_row.operation == "contact_pull"
        assert usage_row.provider == "apollo"
        assert usage_row.client_id == 1
        assert usage_row.entity_id == "comp-uuid"
        assert usage_row.records_returned == 3
        # All 3 people had emails — no reveals needed → credits_estimated = 0
        assert usage_row.credits_estimated == 0
        assert usage_row.credits_used is None

    @pytest.mark.asyncio
    async def test_credits_estimated_nonzero_when_reveals_needed(self):
        """People without email require a reveal call (1 credit each)."""
        people_no_email = [
            {"id": f"p{i}", "first_name": "A", "last_name": "B",
             "email": None, "title": "VP", "organization": {}, "linkedin_url": None}
            for i in range(2)
        ]

        reveal_call_count = 0

        async def fake_post(url, headers, json):
            nonlocal reveal_call_count
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "people/match" in url:
                reveal_call_count += 1
                resp.status_code = 200
                resp.json.return_value = {"person": {"email": f"revealed{reveal_call_count}@x.com"}}
            else:
                resp.json.return_value = {
                    "people": people_no_email,
                    "pagination": {"total_entries": 2},
                }
            return resp

        company = MagicMock()
        company.id = "comp-uuid"
        company.apollo_id = "apollo-org-1"
        company.name = "Acme"

        async def fake_upsert(db, lead_data, client_id):
            lead = MagicMock()
            lead.company_id = company.id
            return lead, "created"

        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=fake_upsert), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            from app.schemas.company import ContactPullFilters
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(
                db, company, client_id=1,
                filters=ContactPullFilters(limit=10),
            )

        usage_row = next(
            (c[0][0] for c in db.add.call_args_list
             if type(c[0][0]).__name__ == "ProviderUsageLog"),
            None,
        )
        assert usage_row is not None
        # 2 reveal attempts → credits_estimated = 2
        assert usage_row.credits_estimated == 2
        assert usage_row.request_count == 3  # 1 search + 2 reveals
        assert usage_row.credits_used is None
