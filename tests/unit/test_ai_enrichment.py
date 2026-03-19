"""Unit tests for AIEnrichmentService.analyze_lead.

Mocks the AI provider at the AnthropicProvider.complete level — never calls
the real API. dynamic_config is patched to return a fixed provider + key so
that tests are fully self-contained.
"""
import json
from contextlib import contextmanager

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import AIConfigurationError, AIEnrichmentError, ConfigurationError
from app.services.ai_enrichment import (
    AIEnrichmentService,
    _CompletionError,
    get_ai_service,
)
from tests.factories import LeadFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_RESPONSE = {
    "company_summary": "Acme Corp makes widgets.",
    "icebreakers": ["Line 1", "Line 2", "Line 3"],
    "qualification": {"rating": "hot", "reasoning": "Strong ICP fit."},
    "email_angle": "Focus on ROI reduction.",
}


@contextmanager
def _ai_mocked(raw_text: str | None = None, side_effect=None):
    """Patch dynamic_config and AnthropicProvider so no real API call is made.

    Yields the mock provider instance.
    """
    response = raw_text if raw_text is not None else json.dumps(VALID_RESPONSE)

    provider_instance = MagicMock()
    if side_effect:
        provider_instance.complete = AsyncMock(side_effect=side_effect)
    else:
        provider_instance.complete = AsyncMock(return_value=response)

    with (
        patch(
            "app.core.dynamic_config.dynamic_config.get_ai_provider",
            new=AsyncMock(return_value="anthropic"),
        ),
        patch(
            "app.core.dynamic_config.dynamic_config.get_key",
            new=AsyncMock(return_value="test-key"),
        ),
        patch(
            "app.services.ai_enrichment.AnthropicProvider",
            return_value=provider_instance,
        ),
    ):
        yield provider_instance


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAIEnrichmentServiceSuccess:

    async def test_returns_all_four_fields(self):
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=1, company="Acme", title="VP Sales")
        with _ai_mocked():
            result = await svc.analyze_lead(lead, MagicMock())
        assert "company_summary" in result
        assert "icebreakers" in result
        assert "qualification" in result
        assert "email_angle" in result

    async def test_icebreakers_is_list(self):
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=1)
        with _ai_mocked():
            result = await svc.analyze_lead(lead, MagicMock())
        assert isinstance(result["icebreakers"], list)
        assert len(result["icebreakers"]) == 3

    async def test_qualification_has_rating_and_reasoning(self):
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=1)
        with _ai_mocked():
            result = await svc.analyze_lead(lead, MagicMock())
        assert result["qualification"]["rating"] in ("hot", "warm", "cold")
        assert isinstance(result["qualification"]["reasoning"], str)


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAIEnrichmentServiceFailures:

    async def test_malformed_json_raises_ai_enrichment_error(self):
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=42)
        with _ai_mocked(raw_text="not json at all {{{"):
            with pytest.raises(AIEnrichmentError) as exc_info:
                await svc.analyze_lead(lead, MagicMock())
        assert exc_info.value.lead_id == 42

    async def test_missing_key_raises_ai_enrichment_error(self):
        incomplete = {"company_summary": "x", "icebreakers": [], "qualification": {}}
        # Missing "email_angle"
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=5)
        with _ai_mocked(raw_text=json.dumps(incomplete)):
            with pytest.raises(AIEnrichmentError) as exc_info:
                await svc.analyze_lead(lead, MagicMock())
        assert exc_info.value.lead_id == 5
        assert "email_angle" in str(exc_info.value)

    async def test_completion_error_raises_ai_enrichment_error(self):
        """_CompletionError from the provider is wrapped as AIEnrichmentError."""
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=7)
        with _ai_mocked(side_effect=_CompletionError("Anthropic connection failed")):
            with pytest.raises(AIEnrichmentError) as exc_info:
                await svc.analyze_lead(lead, MagicMock())
        assert exc_info.value.lead_id == 7

    async def test_rate_limit_completion_error_raises_ai_enrichment_error(self):
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=8)
        with _ai_mocked(side_effect=_CompletionError("Anthropic rate limit exceeded")):
            with pytest.raises(AIEnrichmentError) as exc_info:
                await svc.analyze_lead(lead, MagicMock())
        assert exc_info.value.lead_id == 8

    async def test_status_503_completion_error_raises_ai_enrichment_error(self):
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=9)
        with _ai_mocked(side_effect=_CompletionError("Anthropic API error (HTTP 503)")):
            with pytest.raises(AIEnrichmentError) as exc_info:
                await svc.analyze_lead(lead, MagicMock())
        assert exc_info.value.lead_id == 9
        assert "503" in str(exc_info.value)

    async def test_no_provider_key_raises_ai_configuration_error(self):
        """ConfigurationError from dynamic_config becomes AIConfigurationError."""
        svc = AIEnrichmentService()
        lead = LeadFactory.build(id=10)
        with (
            patch(
                "app.core.dynamic_config.dynamic_config.get_ai_provider",
                new=AsyncMock(side_effect=ConfigurationError("No key configured")),
            ),
        ):
            with pytest.raises(AIConfigurationError):
                await svc.analyze_lead(lead, MagicMock())

    async def test_get_ai_service_returns_instance(self):
        svc = get_ai_service()
        assert isinstance(svc, AIEnrichmentService)
