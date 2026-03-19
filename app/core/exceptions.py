"""Custom exception hierarchy for LeadEngine.

All domain exceptions inherit from LeadEngineError so callers can catch broadly
or narrowly as needed.
"""


class LeadEngineError(Exception):
    """Base class for all LeadEngine domain exceptions."""


class ConfigurationError(LeadEngineError):
    """A required configuration value (e.g. API key, encryption key) is missing or invalid."""


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


class EnrichmentError(LeadEngineError):
    """Base class for enrichment failures."""


class EnrichmentProviderError(EnrichmentError):
    """An enrichment provider returned an error or timed out."""

    def __init__(
        self,
        provider: str,
        lead_id: int,
        reason: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"[{provider}] lead {lead_id}: {reason}")
        self.provider = provider
        self.lead_id = lead_id
        self.reason = reason
        self.cause = cause


class EnrichmentConfigError(EnrichmentError):
    """Required enrichment configuration (e.g. API key) is missing."""

    def __init__(self, provider: str, detail: str) -> None:
        super().__init__(f"[{provider}] configuration error: {detail}")
        self.provider = provider
        self.detail = detail


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class RoutingError(LeadEngineError):
    """Base class for routing failures."""


class GHLWebhookError(RoutingError):
    """GHL webhook POST failed after all retries."""

    def __init__(
        self,
        lead_id: int,
        destination: str,
        reason: str,
        response_code: int | None = None,
    ) -> None:
        super().__init__(
            f"GHL webhook failed for lead {lead_id} -> {destination}: {reason}"
        )
        self.lead_id = lead_id
        self.destination = destination
        self.reason = reason
        self.response_code = response_code


class RoutingConfigError(RoutingError):
    """Required routing configuration (e.g. webhook URL) is missing."""

    def __init__(self, destination: str, detail: str) -> None:
        super().__init__(f"[{destination}] routing config error: {detail}")
        self.destination = destination
        self.detail = detail


# ---------------------------------------------------------------------------
# AI Enrichment
# ---------------------------------------------------------------------------


class AIEnrichmentError(LeadEngineError):
    """Anthropic API call or response parsing failed."""

    def __init__(
        self,
        lead_id: int,
        reason: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"AI analysis failed for lead {lead_id}: {reason}")
        self.lead_id = lead_id
        self.reason = reason
        self.cause = cause


class AIConfigurationError(LeadEngineError):
    """ANTHROPIC_API_KEY is not configured."""


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class ScoringError(LeadEngineError):
    """A scoring rule evaluation raised an unexpected error."""

    def __init__(
        self,
        rule_id: int,
        field: str,
        reason: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"Scoring rule {rule_id} (field={field}): {reason}")
        self.rule_id = rule_id
        self.field = field
        self.reason = reason
        self.cause = cause


# ---------------------------------------------------------------------------
# Dead Letter
# ---------------------------------------------------------------------------


class DeadLetterError(LeadEngineError):
    """Failed to write or read from the dead letter queue."""
