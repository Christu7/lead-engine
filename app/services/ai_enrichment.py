import json
import logging
import time
from datetime import datetime, timezone

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

AI_DL_QUEUE_KEY = "ai_analysis_dead_letters"

SYSTEM_PROMPT = """\
You are an expert B2B sales researcher. Analyze the provided lead data and respond with \
a single JSON object. Return ONLY the JSON object — no preamble, no explanation, \
no markdown, no code blocks.

The JSON must have exactly these top-level keys:
- "company_summary": (string) One paragraph about the company and what they do.
- "icebreakers": (array of exactly 3 strings) Personalized outreach opening lines \
specific to this person's role and company — not generic.
- "qualification": (object) with exactly two keys:
    - "rating": one of "hot", "warm", or "cold"
    - "reasoning": 2-3 sentences explaining the rating
- "email_angle": (string) One paragraph on the best cold email angle based on their \
role and company context.
"""


class AIEnrichmentError(Exception):
    """Raised when the Anthropic API call or response parsing fails."""

    def __init__(self, message: str, lead_id: int, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.lead_id = lead_id
        self.cause = cause


class ConfigurationError(Exception):
    """Raised when ANTHROPIC_API_KEY is not set."""


class AIEnrichmentService:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=30.0)

    def _build_lead_context(self, lead) -> str:
        """Build a compact JSON context from all non-empty lead fields."""
        data: dict = {}

        # Core lead fields — only include if present
        for field in ("name", "title", "company", "phone", "source"):
            value = getattr(lead, field, None)
            if value:
                data[field] = value

        enrichment = lead.enrichment_data or {}

        # Apollo data
        apollo = enrichment.get("apollo", {})
        if apollo.get("linkedin_url"):
            data["linkedin_url"] = apollo["linkedin_url"]
        if apollo.get("industry"):
            data["industry"] = apollo["industry"]
        if apollo.get("company_size"):
            data["company_size"] = apollo["company_size"]
        if apollo.get("company_description"):
            data["company_description"] = apollo["company_description"]

        # Clearbit data (fills gaps not already set by Apollo)
        cb_company = enrichment.get("clearbit", {}).get("company", {})
        if cb_company.get("description"):
            data.setdefault("company_description", cb_company["description"])
        if cb_company.get("employees"):
            data.setdefault("company_size", cb_company["employees"])
        if cb_company.get("industry"):
            data.setdefault("industry", cb_company["industry"])

        # Proxycurl / LinkedIn data
        proxycurl = enrichment.get("proxycurl", {})
        if proxycurl.get("summary"):
            data["linkedin_summary"] = proxycurl["summary"]
        if proxycurl.get("headline"):
            data["linkedin_headline"] = proxycurl["headline"]

        return json.dumps(data, indent=2)

    async def analyze_lead(self, lead) -> dict:
        """Call the Anthropic API and return the parsed analysis dict.

        Raises AIEnrichmentError on any API or parsing failure.
        Never returns None and never silently swallows errors.
        """
        context = self._build_lead_context(lead)

        try:
            message = await self._client.messages.create(
                model="claude-sonnet-4-5-20251022",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Lead data:\n\n{context}"}],
            )
        except anthropic.APIConnectionError as exc:
            raise AIEnrichmentError(
                f"Anthropic connection failed: {exc}",
                lead_id=lead.id,
                cause=exc,
            ) from exc
        except anthropic.RateLimitError as exc:
            raise AIEnrichmentError(
                "Anthropic rate limit exceeded",
                lead_id=lead.id,
                cause=exc,
            ) from exc
        except anthropic.APIStatusError as exc:
            raise AIEnrichmentError(
                f"Anthropic API error (HTTP {exc.status_code}): {exc.message}",
                lead_id=lead.id,
                cause=exc,
            ) from exc

        raw_text = message.content[0].text

        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AIEnrichmentError(
                f"Could not parse Anthropic response as JSON. Got: {raw_text[:300]}",
                lead_id=lead.id,
                cause=exc,
            ) from exc

        required_keys = {"company_summary", "icebreakers", "qualification", "email_angle"}
        missing = required_keys - set(result.keys())
        if missing:
            raise AIEnrichmentError(
                f"Anthropic response missing required keys: {sorted(missing)}",
                lead_id=lead.id,
            )

        return result


def get_ai_service() -> AIEnrichmentService:
    """Return a configured AIEnrichmentService.

    Raises ConfigurationError immediately if ANTHROPIC_API_KEY is not set,
    so callers receive a clear error rather than a cryptic auth failure at
    request time.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise ConfigurationError(
            "ANTHROPIC_API_KEY is not configured. Set it in .env to enable AI analysis."
        )
    return AIEnrichmentService(settings.ANTHROPIC_API_KEY)


async def run_analysis_for_lead(lead_id: int, client_id: int) -> None:
    """Run AI analysis for a lead, managing its own DB session.

    Safe to call from FastAPI BackgroundTasks or directly from the worker.
    Sets ai_status throughout and writes failures to the dead letter queue.
    """
    # Deferred imports to avoid circular dependencies at module load time
    from app.core.database import async_session
    from app.core.redis import redis
    from app.models.lead import Lead

    async with async_session() as db:
        lead = await db.get(Lead, lead_id)
        if not lead:
            logger.error(
                "AI analysis: lead not found",
                extra={"lead_id": lead_id, "client_id": client_id},
            )
            return

        # Multi-tenancy check: never analyze a lead for the wrong client
        if lead.client_id != client_id:
            logger.error(
                "AI analysis: client_id mismatch — aborting",
                extra={
                    "lead_id": lead_id,
                    "expected_client_id": client_id,
                    "actual_client_id": lead.client_id,
                },
            )
            return

        lead.ai_status = "analyzing"
        await db.commit()

        logger.info(
            "AI analysis started",
            extra={"lead_id": lead_id, "client_id": client_id},
        )
        start = time.perf_counter()

        try:
            service = get_ai_service()
            result = await service.analyze_lead(lead)

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            lead.ai_analysis = result
            lead.ai_status = "completed"
            lead.ai_analyzed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "AI analysis completed",
                extra={"lead_id": lead_id, "client_id": client_id, "duration_ms": duration_ms},
            )

        except (AIEnrichmentError, ConfigurationError) as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "AI analysis failed: %s",
                str(exc),
                extra={"lead_id": lead_id, "client_id": client_id, "duration_ms": duration_ms},
            )
            lead.ai_status = "failed"
            await db.commit()

            # Write to dead letter queue so admins can retry
            payload = json.dumps(
                {"lead_id": lead_id, "client_id": client_id, "error": str(exc)}
            )
            await redis.lpush(AI_DL_QUEUE_KEY, payload)
