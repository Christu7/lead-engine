"""Unit tests for route_lead.

Uses respx to mock GHL webhook HTTP calls and AsyncMock for the DB session.
"""
import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import ConfigurationError
from app.models.client import Client
from app.models.lead import Lead, RoutingLog
from app.services.routing import _build_ghl_payload, route_lead
from tests.factories import ClientFactory, LeadFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GHL_INBOUND = "https://hooks.ghl.example.com/inbound"
GHL_OUTBOUND = "https://hooks.ghl.example.com/outbound"

ROUTING_SETTINGS = {
    "routing": {
        "score_inbound_threshold": 70,
        "score_outbound_threshold": 40,
        "ghl_inbound_webhook_url": GHL_INBOUND,
        "ghl_outbound_webhook_url": GHL_OUTBOUND,
    }
}


def _make_db(lead: Lead, client: Client):
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def mock_get(model, pk):
        if model is Client:
            return client
        return None

    db.get = AsyncMock(side_effect=mock_get)
    return db


# ---------------------------------------------------------------------------
# Payload tests (pure, no DB/HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildGhlPayload:
    def test_splits_name_into_first_last(self):
        lead = LeadFactory.build(name="Jane Doe", email="jane@example.com")
        payload = _build_ghl_payload(lead)
        assert payload["firstName"] == "Jane"
        assert payload["lastName"] == "Doe"

    def test_single_name_sets_first_only(self):
        lead = LeadFactory.build(name="Mononym", email="mono@example.com")
        payload = _build_ghl_payload(lead)
        assert payload["firstName"] == "Mononym"
        assert payload["lastName"] == ""

    def test_payload_contains_required_fields(self):
        lead = LeadFactory.build(
            name="Alice Smith", email="alice@example.com", score=80
        )
        payload = _build_ghl_payload(lead)
        assert "email" in payload
        assert "phone" in payload
        assert "tags" in payload
        assert "customField" in payload
        assert payload["customField"]["score"] == 80


# ---------------------------------------------------------------------------
# Routing destination tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouteLeadDestination:

    @respx.mock
    async def test_high_score_routes_to_inbound(self):
        lead = LeadFactory.build(id=1, client_id=1, score=80)
        client = ClientFactory.build(id=1, settings=ROUTING_SETTINGS)
        db = _make_db(lead, client)

        respx.post(GHL_INBOUND).mock(return_value=httpx.Response(200))

        with patch("app.services.dead_letter.DeadLetterService.push", AsyncMock()):
            result = await route_lead(db, lead, 1)

        assert result.destination == "ghl_inbound"
        assert result.status == "routed"

    @respx.mock
    async def test_mid_score_routes_to_outbound(self):
        lead = LeadFactory.build(id=1, client_id=1, score=55)
        client = ClientFactory.build(id=1, settings=ROUTING_SETTINGS)
        db = _make_db(lead, client)

        respx.post(GHL_OUTBOUND).mock(return_value=httpx.Response(200))

        with patch("app.services.dead_letter.DeadLetterService.push", AsyncMock()):
            result = await route_lead(db, lead, 1)

        assert result.destination == "ghl_outbound"
        assert result.status == "routed"

    async def test_low_score_routes_to_manual_review(self):
        lead = LeadFactory.build(id=1, client_id=1, score=20)
        client = ClientFactory.build(id=1, settings=ROUTING_SETTINGS)
        db = _make_db(lead, client)

        result = await route_lead(db, lead, 1)

        assert result.destination == "manual_review"
        assert result.status == "manual_review"
        db.add.assert_called_once()
        log: RoutingLog = db.add.call_args[0][0]
        assert log.destination == "manual_review"

    async def test_no_webhook_url_returns_no_config(self):
        lead = LeadFactory.build(id=1, client_id=1, score=80)
        client = ClientFactory.build(
            id=1,
            settings={
                "routing": {
                    "score_inbound_threshold": 70,
                    "score_outbound_threshold": 40,
                    # no ghl_inbound_webhook_url
                }
            },
        )
        db = _make_db(lead, client)

        # No global key in ApiKeyStore either — dynamic_config should raise ConfigurationError
        with patch(
            "app.services.routing.dynamic_config.get_key",
            AsyncMock(side_effect=ConfigurationError("no key")),
        ):
            result = await route_lead(db, lead, 1)

        assert result.status == "no_config"
        assert result.destination == "ghl_inbound"


# ---------------------------------------------------------------------------
# GHL failure / retry tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouteLeadFailures:

    @respx.mock
    async def test_ghl_500_marks_failed_and_writes_dead_letter(self):
        lead = LeadFactory.build(id=1, client_id=1, score=80)
        client = ClientFactory.build(id=1, settings=ROUTING_SETTINGS)
        db = _make_db(lead, client)

        # All retries return 500
        respx.post(GHL_INBOUND).mock(return_value=httpx.Response(500, text="error"))

        mock_dl_push = AsyncMock()
        with (
            patch("app.services.dead_letter.DeadLetterService.push", mock_dl_push),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await route_lead(db, lead, 1)

        assert result.status == "failed"
        mock_dl_push.assert_awaited_once()

    @respx.mock
    async def test_ghl_timeout_marks_failed_and_writes_dead_letter(self):
        lead = LeadFactory.build(id=1, client_id=1, score=80)
        client = ClientFactory.build(id=1, settings=ROUTING_SETTINGS)
        db = _make_db(lead, client)

        respx.post(GHL_INBOUND).mock(side_effect=httpx.TimeoutException("timeout"))

        mock_dl_push = AsyncMock()
        with (
            patch("app.services.dead_letter.DeadLetterService.push", mock_dl_push),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await route_lead(db, lead, 1)

        assert result.status == "failed"
        mock_dl_push.assert_awaited_once()

    @respx.mock
    async def test_retry_succeeds_on_second_attempt(self):
        """First call fails, second succeeds — result should be 'routed'."""
        lead = LeadFactory.build(id=1, client_id=1, score=80)
        client = ClientFactory.build(id=1, settings=ROUTING_SETTINGS)
        db = _make_db(lead, client)

        route = respx.post(GHL_INBOUND)
        route.side_effect = [
            httpx.Response(500, text="err"),
            httpx.Response(200),
        ]

        with (
            patch("app.services.dead_letter.DeadLetterService.push", AsyncMock()),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await route_lead(db, lead, 1)

        assert result.status == "routed"

    @respx.mock
    async def test_routing_log_written_on_success(self):
        lead = LeadFactory.build(id=1, client_id=1, score=80)
        client = ClientFactory.build(id=1, settings=ROUTING_SETTINGS)
        db = _make_db(lead, client)

        respx.post(GHL_INBOUND).mock(return_value=httpx.Response(200))

        with (
            patch("app.services.dead_letter.DeadLetterService.push", AsyncMock()),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await route_lead(db, lead, 1)

        db.add.assert_called_once()
        log: RoutingLog = db.add.call_args[0][0]
        assert log.success is True
        assert log.destination == "ghl_inbound"
        assert log.response_code == 200
