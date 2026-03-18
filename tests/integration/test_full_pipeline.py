"""Integration tests for the full lead pipeline.

These tests run the enrichment pipeline against a real test database,
mocking only external HTTP calls (Apollo, GHL webhooks) via respx.
"""
import pytest
import respx
import httpx
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.models.lead import Lead, EnrichmentLog, RoutingLog
from app.services.enrichment.pipeline import EnrichmentPipeline
from app.services.enrichment.providers.apollo import ApolloProvider
from app.services.enrichment import DEFAULT_PROVIDERS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_lead(db_session, client, email: str = "test@example.com") -> Lead:
    from app.models.lead import Lead as LeadModel

    lead = LeadModel(
        client_id=client.id,
        name="Test User",
        email=email,
        status="new",
        enrichment_status="pending",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


async def _create_client_with_keys(db_session, inbound_url: str | None = None) -> object:
    from app.models.client import Client

    routing = {}
    if inbound_url:
        routing = {
            "score_inbound_threshold": 0,  # always route inbound for tests
            "score_outbound_threshold": -1,
            "ghl_inbound_webhook_url": inbound_url,
        }

    client = Client(
        name="Pipeline Client",
        settings={
            "enrichment": {"apollo_api_key": "fake-apollo-key"},
            "routing": routing,
        },
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullPipelineHappyPath:

    @respx.mock
    async def test_ingest_enrich_score_route(self, db_session):
        """Full pipeline: lead created → enriched via Apollo → scored → routed to GHL."""
        ghl_url = "https://ghl.test/webhook/inbound"
        client = await _create_client_with_keys(db_session, inbound_url=ghl_url)
        lead = await _create_lead(db_session, client)

        respx.post("https://api.apollo.io/api/v1/people/match").mock(
            return_value=httpx.Response(
                200,
                json={
                    "person": {
                        "title": "VP Engineering",
                        "organization": {"name": "Acme Corp"},
                    }
                },
            )
        )
        respx.post(ghl_url).mock(return_value=httpx.Response(200))

        with (
            patch(
                "app.services.enrichment.pipeline.get_cached",
                AsyncMock(return_value=None),
            ),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.rate_limiter") as mock_rl,
        ):
            mock_rl.acquire = AsyncMock(return_value=True)
            pipeline = EnrichmentPipeline([ApolloProvider()])
            await pipeline.run(db_session, lead.id, client.id)

        await db_session.refresh(lead)
        assert lead.enrichment_status == "enriched"
        assert lead.enrichment_data is not None
        assert lead.score is not None

        # EnrichmentLog created
        result = await db_session.execute(
            select(EnrichmentLog).where(EnrichmentLog.lead_id == lead.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].success is True

        # RoutingLog created
        result = await db_session.execute(
            select(RoutingLog).where(RoutingLog.lead_id == lead.id)
        )
        routing_logs = result.scalars().all()
        assert len(routing_logs) == 1
        assert routing_logs[0].success is True


# ---------------------------------------------------------------------------
# Partial / failed enrichment
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEnrichmentFailures:

    @respx.mock
    async def test_apollo_failure_sets_failed_status(self, db_session):
        client = await _create_client_with_keys(db_session)
        lead = await _create_lead(db_session, client)

        respx.post("https://api.apollo.io/api/v1/people/match").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with (
            patch(
                "app.services.enrichment.pipeline.get_cached",
                AsyncMock(return_value=None),
            ),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.rate_limiter") as mock_rl,
            patch("app.services.enrichment.pipeline.score_lead", AsyncMock(return_value=0)),
            patch("app.services.enrichment.pipeline.route_lead", AsyncMock()),
            patch("app.services.dead_letter.DeadLetterService.push", AsyncMock()),
        ):
            mock_rl.acquire = AsyncMock(return_value=True)
            pipeline = EnrichmentPipeline([ApolloProvider()])
            await pipeline.run(db_session, lead.id, client.id)

        await db_session.refresh(lead)
        assert lead.enrichment_status == "failed"

        # EnrichmentLog created with success=False
        result = await db_session.execute(
            select(EnrichmentLog).where(EnrichmentLog.lead_id == lead.id)
        )
        logs = result.scalars().all()
        assert len(logs) >= 1
        assert all(not log.success for log in logs)


# ---------------------------------------------------------------------------
# Routing failure → dead letter
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRoutingFailure:

    @respx.mock
    async def test_routing_failure_creates_routing_log_with_failure(self, db_session):
        ghl_url = "https://ghl.test/fail"
        client = await _create_client_with_keys(db_session, inbound_url=ghl_url)
        lead = await _create_lead(db_session, client)

        respx.post("https://api.apollo.io/api/v1/people/match").mock(
            return_value=httpx.Response(
                200,
                json={"person": {"title": "CEO", "organization": {"name": "TestCo"}}},
            )
        )
        # GHL always fails
        respx.post(ghl_url).mock(return_value=httpx.Response(500, text="err"))

        mock_dl_push = AsyncMock()

        with (
            patch(
                "app.services.enrichment.pipeline.get_cached",
                AsyncMock(return_value=None),
            ),
            patch("app.services.enrichment.pipeline.set_cached", AsyncMock()),
            patch("app.services.enrichment.pipeline.rate_limiter") as mock_rl,
            patch("app.services.dead_letter.DeadLetterService.push", mock_dl_push),
        ):
            mock_rl.acquire = AsyncMock(return_value=True)
            pipeline = EnrichmentPipeline([ApolloProvider()])
            await pipeline.run(db_session, lead.id, client.id)

        await db_session.refresh(lead)
        # Enrichment succeeded even though routing failed
        assert lead.enrichment_status == "enriched"

        result = await db_session.execute(
            select(RoutingLog).where(RoutingLog.lead_id == lead.id)
        )
        routing_logs = result.scalars().all()
        assert len(routing_logs) >= 1
        assert any(not log.success for log in routing_logs)

        # Dead letter was pushed for routing failure
        mock_dl_push.assert_awaited_once()


# ---------------------------------------------------------------------------
# AI analysis status transitions
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAIAnalysisTransitions:

    async def test_ai_analysis_sets_completed_on_success(self, db_session, seeded_client):
        from app.services.ai_enrichment import run_analysis_for_lead
        from app.core import database as db_module

        lead = await _create_lead(db_session, seeded_client, email="ai@test.com")

        mock_result = {
            "company_summary": "A great company.",
            "icebreakers": ["Hi", "Hey", "Hello"],
            "qualification": {"rating": "hot", "reasoning": "Strong fit."},
            "email_angle": "Focus on pain points.",
        }

        def _fake_session_factory():
            class _CM:
                async def __aenter__(self):
                    return db_session

                async def __aexit__(self, *args):
                    pass

            return _CM()

        with (
            patch("app.services.ai_enrichment.get_ai_service") as mock_get_svc,
            patch.object(db_module, "async_session", new=_fake_session_factory),
        ):
            mock_svc = mock_get_svc.return_value
            mock_svc.analyze_lead = AsyncMock(return_value=mock_result)
            await run_analysis_for_lead(lead.id, seeded_client.id)

        await db_session.refresh(lead)
        assert lead.ai_status == "completed"
        assert lead.ai_analysis is not None
        assert lead.ai_analyzed_at is not None

    async def test_ai_analysis_sets_failed_on_error(self, db_session, seeded_client):
        from app.services.ai_enrichment import run_analysis_for_lead
        from app.core.exceptions import AIEnrichmentError
        from app.core import database as db_module

        lead = await _create_lead(db_session, seeded_client, email="aifail@test.com")

        def _fake_session_factory():
            class _CM:
                async def __aenter__(self):
                    return db_session

                async def __aexit__(self, *args):
                    pass

            return _CM()

        with (
            patch("app.services.ai_enrichment.get_ai_service") as mock_get_svc,
            patch.object(db_module, "async_session", new=_fake_session_factory),
            patch("app.services.dead_letter.DeadLetterService.push", AsyncMock()),
        ):
            mock_svc = mock_get_svc.return_value
            mock_svc.analyze_lead = AsyncMock(
                side_effect=AIEnrichmentError(lead_id=lead.id, reason="Simulated failure")
            )
            await run_analysis_for_lead(lead.id, seeded_client.id)

        await db_session.refresh(lead)
        assert lead.ai_status == "failed"
