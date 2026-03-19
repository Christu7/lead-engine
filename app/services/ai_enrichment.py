import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AIConfigurationError, AIEnrichmentError, ConfigurationError

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


class _CompletionError(Exception):
    """Internal: raised by providers when the API call fails. Wraps provider-specific errors."""


class AIProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str) -> str:
        """Call the AI API and return the raw text response.

        Raises _CompletionError on any API or network failure.
        """


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=30.0)

    async def complete(self, prompt: str, system: str) -> str:
        try:
            message = await self._client.messages.create(
                model="claude-sonnet-4-5-20251022",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIConnectionError as exc:
            raise _CompletionError(f"Anthropic connection failed: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise _CompletionError("Anthropic rate limit exceeded") from exc
        except anthropic.APIStatusError as exc:
            raise _CompletionError(
                f"Anthropic API error (HTTP {exc.status_code}): {exc.message}"
            ) from exc
        return message.content[0].text


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI  # deferred: not all installs have openai

        self._client = AsyncOpenAI(api_key=api_key, timeout=30.0)

    async def complete(self, prompt: str, system: str) -> str:
        try:
            import openai

            resp = await self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
        except openai.APIConnectionError as exc:
            raise _CompletionError(f"OpenAI connection failed: {exc}") from exc
        except openai.RateLimitError as exc:
            raise _CompletionError("OpenAI rate limit exceeded") from exc
        except openai.APIStatusError as exc:
            raise _CompletionError(
                f"OpenAI API error (HTTP {exc.status_code}): {exc.message}"
            ) from exc
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class AIEnrichmentService:
    def _build_lead_context(self, lead) -> str:
        """Build a compact JSON context from all non-empty lead fields."""
        data: dict = {}

        for field in ("name", "title", "company", "phone", "source"):
            value = getattr(lead, field, None)
            if value:
                data[field] = value

        enrichment = lead.enrichment_data or {}

        apollo = enrichment.get("apollo", {})
        if apollo.get("linkedin_url"):
            data["linkedin_url"] = apollo["linkedin_url"]
        if apollo.get("industry"):
            data["industry"] = apollo["industry"]
        if apollo.get("company_size"):
            data["company_size"] = apollo["company_size"]
        if apollo.get("company_description"):
            data["company_description"] = apollo["company_description"]

        clearbit = enrichment.get("clearbit", {})
        if clearbit.get("description"):
            data.setdefault("company_description", clearbit["description"])
        if clearbit.get("employee_count"):
            data.setdefault("company_size", clearbit["employee_count"])
        if clearbit.get("industry"):
            data.setdefault("industry", clearbit["industry"])

        proxycurl = enrichment.get("proxycurl", {})
        if proxycurl.get("summary"):
            data["linkedin_summary"] = proxycurl["summary"]
        if proxycurl.get("headline"):
            data["linkedin_headline"] = proxycurl["headline"]

        return json.dumps(data, indent=2)

    async def analyze_lead(self, lead, db: AsyncSession) -> dict:
        """Call the configured AI provider and return the parsed analysis dict.

        Raises AIEnrichmentError on API or parsing failure.
        Raises AIConfigurationError if no AI provider key is configured.
        Never returns None and never silently swallows errors.
        """
        from app.core.dynamic_config import dynamic_config

        context = self._build_lead_context(lead)
        prompt = f"Lead data:\n\n{context}"

        # Resolve provider at call time
        try:
            provider_name = await dynamic_config.get_ai_provider(db)
            api_key = await dynamic_config.get_key(db, provider_name)
        except ConfigurationError as exc:
            raise AIConfigurationError(str(exc)) from exc

        if provider_name == "openai":
            provider: AIProvider = OpenAIProvider(api_key)
        else:
            provider = AnthropicProvider(api_key)

        try:
            raw_text = await provider.complete(prompt, SYSTEM_PROMPT)
        except _CompletionError as exc:
            raise AIEnrichmentError(
                lead_id=lead.id,
                reason=str(exc),
                cause=exc.__cause__,
            ) from exc

        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AIEnrichmentError(
                lead_id=lead.id,
                reason=f"Could not parse {provider_name} response as JSON. Got: {raw_text[:300]}",
                cause=exc,
            ) from exc

        required_keys = {"company_summary", "icebreakers", "qualification", "email_angle"}
        missing = required_keys - set(result.keys())
        if missing:
            raise AIEnrichmentError(
                lead_id=lead.id,
                reason=f"{provider_name} response missing required keys: {sorted(missing)}",
            )

        logger.debug(
            "AI analysis provider used",
            extra={"lead_id": lead.id, "provider": provider_name},
        )
        return result


def get_ai_service() -> AIEnrichmentService:
    """Return an AIEnrichmentService instance.

    Key validation happens at analyze_lead() time, not here.
    """
    return AIEnrichmentService()


async def run_analysis_for_lead(lead_id: int, client_id: int) -> None:
    """Run AI analysis for a lead, managing its own DB session.

    Safe to call from FastAPI BackgroundTasks or directly from the worker.
    Sets ai_status throughout and writes failures to the dead letter queue.
    """
    from app.core.database import async_session
    from app.core.redis import redis
    from app.models.lead import Lead
    from app.services.dead_letter import DeadLetterService, DeadLetterType

    async with async_session() as db:
        lead = await db.get(Lead, lead_id)
        if not lead:
            logger.error(
                "AI analysis: lead not found",
                extra={"lead_id": lead_id, "client_id": client_id},
            )
            return

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
            result = await service.analyze_lead(lead, db)

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            lead.ai_analysis = result
            lead.ai_status = "completed"
            lead.ai_analyzed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "AI analysis completed",
                extra={"lead_id": lead_id, "client_id": client_id, "duration_ms": duration_ms},
            )

        except (AIEnrichmentError, AIConfigurationError) as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "AI analysis failed: %s",
                str(exc),
                extra={"lead_id": lead_id, "client_id": client_id, "duration_ms": duration_ms},
            )
            lead.ai_status = "failed"
            await db.commit()

            try:
                dl_svc = DeadLetterService(redis)
                await dl_svc.push(
                    DeadLetterType.AI_ANALYSIS,
                    lead_id=lead_id,
                    client_id=client_id,
                    error=str(exc),
                )
            except Exception as dl_exc:
                logger.error(
                    "AI analysis: failed to write dead letter for lead %d: %s",
                    lead_id,
                    dl_exc,
                )

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "AI analysis: unexpected error for lead %d",
                lead_id,
                extra={"lead_id": lead_id, "client_id": client_id, "duration_ms": duration_ms},
            )
            lead.ai_status = "failed"
            try:
                await db.commit()
            except Exception:
                pass
            try:
                dl_svc = DeadLetterService(redis)
                await dl_svc.push(
                    DeadLetterType.AI_ANALYSIS,
                    lead_id=lead_id,
                    client_id=client_id,
                    error=f"Unexpected error: {exc}",
                )
            except Exception as dl_exc:
                logger.error(
                    "AI analysis: failed to write dead letter for lead %d: %s",
                    lead_id,
                    dl_exc,
                )
