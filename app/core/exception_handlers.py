import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import (
    AIConfigurationError,
    AIEnrichmentError,
    DeadLetterError,
    EnrichmentConfigError,
    EnrichmentProviderError,
    GHLWebhookError,
    LeadEngineError,
    RoutingConfigError,
    ScoringError,
)

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    error: str,
    message: str,
    lead_id: int | None = None,
    tb: str | None = None,
) -> JSONResponse:
    body: dict = {"error": error, "message": message}
    if lead_id is not None:
        body["lead_id"] = lead_id
    if tb is not None:
        body["traceback"] = tb
    return JSONResponse(status_code=status_code, content=body)


def _maybe_tb() -> str | None:
    return traceback.format_exc() if settings.DEBUG else None


async def enrichment_provider_error_handler(
    request: Request, exc: EnrichmentProviderError
) -> JSONResponse:
    logger.error(
        "EnrichmentProviderError: %s",
        str(exc),
        extra={"lead_id": exc.lead_id, "provider": exc.provider},
    )
    return _error_response(
        502, "enrichment_provider_error", str(exc), lead_id=exc.lead_id, tb=_maybe_tb()
    )


async def enrichment_config_error_handler(
    request: Request, exc: EnrichmentConfigError
) -> JSONResponse:
    logger.error("EnrichmentConfigError: %s", str(exc))
    return _error_response(500, "enrichment_config_error", str(exc), tb=_maybe_tb())


async def ghl_webhook_error_handler(
    request: Request, exc: GHLWebhookError
) -> JSONResponse:
    logger.error(
        "GHLWebhookError: %s",
        str(exc),
        extra={"lead_id": exc.lead_id, "destination": exc.destination},
    )
    return _error_response(
        502, "ghl_webhook_error", str(exc), lead_id=exc.lead_id, tb=_maybe_tb()
    )


async def routing_config_error_handler(
    request: Request, exc: RoutingConfigError
) -> JSONResponse:
    logger.error("RoutingConfigError: %s", str(exc))
    return _error_response(500, "routing_config_error", str(exc), tb=_maybe_tb())


async def ai_enrichment_error_handler(
    request: Request, exc: AIEnrichmentError
) -> JSONResponse:
    logger.error(
        "AIEnrichmentError: %s",
        str(exc),
        extra={"lead_id": exc.lead_id},
    )
    return _error_response(
        502, "ai_enrichment_error", str(exc), lead_id=exc.lead_id, tb=_maybe_tb()
    )


async def ai_configuration_error_handler(
    request: Request, exc: AIConfigurationError
) -> JSONResponse:
    logger.error("AIConfigurationError: %s", str(exc))
    return _error_response(500, "ai_configuration_error", str(exc), tb=_maybe_tb())


async def scoring_error_handler(request: Request, exc: ScoringError) -> JSONResponse:
    logger.error(
        "ScoringError: %s",
        str(exc),
        extra={"rule_id": exc.rule_id, "field": exc.field},
    )
    return _error_response(500, "scoring_error", str(exc), tb=_maybe_tb())


async def dead_letter_error_handler(
    request: Request, exc: DeadLetterError
) -> JSONResponse:
    logger.error("DeadLetterError: %s", str(exc))
    return _error_response(500, "dead_letter_error", str(exc), tb=_maybe_tb())


async def leadengine_error_handler(
    request: Request, exc: LeadEngineError
) -> JSONResponse:
    """Catch-all for any LeadEngineError subclass not handled by a more specific handler."""
    logger.error("LeadEngineError: %s", str(exc))
    return _error_response(500, "internal_error", str(exc), tb=_maybe_tb())


def register_exception_handlers(app) -> None:
    """Register all custom exception handlers on the FastAPI app."""
    # Specific handlers first — FastAPI matches from most- to least-specific
    app.add_exception_handler(EnrichmentProviderError, enrichment_provider_error_handler)
    app.add_exception_handler(EnrichmentConfigError, enrichment_config_error_handler)
    app.add_exception_handler(GHLWebhookError, ghl_webhook_error_handler)
    app.add_exception_handler(RoutingConfigError, routing_config_error_handler)
    app.add_exception_handler(AIEnrichmentError, ai_enrichment_error_handler)
    app.add_exception_handler(AIConfigurationError, ai_configuration_error_handler)
    app.add_exception_handler(ScoringError, scoring_error_handler)
    app.add_exception_handler(DeadLetterError, dead_letter_error_handler)
    # Catch-all must be last
    app.add_exception_handler(LeadEngineError, leadengine_error_handler)
