"""Unit tests for AIEnrichmentService.analyze_lead.

Mocks the Anthropic client — never calls the real API.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import AIConfigurationError, AIEnrichmentError
from app.services.ai_enrichment import AIEnrichmentService, get_ai_service
from tests.factories import LeadFactory

import anthropic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_RESPONSE = {
    "company_summary": "Acme Corp makes widgets.",
    "icebreakers": ["Line 1", "Line 2", "Line 3"],
    "qualification": {"rating": "hot", "reasoning": "Strong ICP fit."},
    "email_angle": "Focus on ROI reduction.",
}


def _make_service(raw_text: str | None = None, side_effect=None) -> AIEnrichmentService:
    """Return an AIEnrichmentService whose Anthropic client is mocked."""
    svc = AIEnrichmentService(api_key="test-key")
    msg = MagicMock()
    msg.content = [MagicMock(text=raw_text or json.dumps(VALID_RESPONSE))]

    if side_effect:
        svc._client.messages.create = AsyncMock(side_effect=side_effect)
    else:
        svc._client.messages.create = AsyncMock(return_value=msg)
    return svc


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAIEnrichmentServiceSuccess:

    async def test_returns_all_four_fields(self):
        svc = _make_service()
        lead = LeadFactory.build(id=1, company="Acme", title="VP Sales")
        result = await svc.analyze_lead(lead)
        assert "company_summary" in result
        assert "icebreakers" in result
        assert "qualification" in result
        assert "email_angle" in result

    async def test_icebreakers_is_list(self):
        svc = _make_service()
        lead = LeadFactory.build(id=1)
        result = await svc.analyze_lead(lead)
        assert isinstance(result["icebreakers"], list)
        assert len(result["icebreakers"]) == 3

    async def test_qualification_has_rating_and_reasoning(self):
        svc = _make_service()
        lead = LeadFactory.build(id=1)
        result = await svc.analyze_lead(lead)
        assert result["qualification"]["rating"] in ("hot", "warm", "cold")
        assert isinstance(result["qualification"]["reasoning"], str)


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAIEnrichmentServiceFailures:

    async def test_malformed_json_raises_ai_enrichment_error(self):
        svc = _make_service(raw_text="not json at all {{{")
        lead = LeadFactory.build(id=42)
        with pytest.raises(AIEnrichmentError) as exc_info:
            await svc.analyze_lead(lead)
        assert exc_info.value.lead_id == 42

    async def test_missing_key_raises_ai_enrichment_error(self):
        incomplete = {"company_summary": "x", "icebreakers": [], "qualification": {}}
        # Missing "email_angle"
        svc = _make_service(raw_text=json.dumps(incomplete))
        lead = LeadFactory.build(id=5)
        with pytest.raises(AIEnrichmentError) as exc_info:
            await svc.analyze_lead(lead)
        assert exc_info.value.lead_id == 5
        assert "email_angle" in str(exc_info.value)

    async def test_api_connection_error_raises_ai_enrichment_error(self):
        svc = _make_service(side_effect=anthropic.APIConnectionError(request=MagicMock()))
        lead = LeadFactory.build(id=7)
        with pytest.raises(AIEnrichmentError) as exc_info:
            await svc.analyze_lead(lead)
        assert exc_info.value.lead_id == 7

    async def test_rate_limit_error_raises_ai_enrichment_error(self):
        svc = _make_service(
            side_effect=anthropic.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429),
                body={},
            )
        )
        lead = LeadFactory.build(id=8)
        with pytest.raises(AIEnrichmentError) as exc_info:
            await svc.analyze_lead(lead)
        assert exc_info.value.lead_id == 8

    async def test_api_status_503_raises_ai_enrichment_error(self):
        svc = _make_service(
            side_effect=anthropic.APIStatusError(
                message="service unavailable",
                response=MagicMock(status_code=503),
                body={},
            )
        )
        lead = LeadFactory.build(id=9)
        with pytest.raises(AIEnrichmentError) as exc_info:
            await svc.analyze_lead(lead)
        assert exc_info.value.lead_id == 9
        assert "503" in str(exc_info.value)

    async def test_empty_api_key_raises_configuration_error(self):
        with patch("app.services.ai_enrichment.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = ""
            with pytest.raises(AIConfigurationError):
                get_ai_service()

    async def test_configured_key_returns_service(self):
        with patch("app.services.ai_enrichment.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "sk-real-key"
            svc = get_ai_service()
        assert isinstance(svc, AIEnrichmentService)
