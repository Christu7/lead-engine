"""Apollo organization enrichment and contact pull for Company records."""
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dynamic_config import dynamic_config
from app.core.exceptions import ConfigurationError, EnrichmentProviderError
from app.models.company import Company
from app.schemas.lead import LeadCreate
from app.services.company import auto_link_leads_by_domain, _normalize_domain
from app.services.lead import upsert_lead

logger = logging.getLogger(__name__)

_APOLLO_BASE_HEADERS = {
    "Content-Type": "application/json",
}


async def _apollo_headers(db: AsyncSession) -> dict:
    """Resolve Apollo API key via dynamic_config and return request headers."""
    try:
        api_key = await dynamic_config.get_key(db, "apollo")
    except ConfigurationError as exc:
        raise EnrichmentProviderError(
            provider="apollo_org",
            lead_id=0,  # not yet known at header-build time
            reason=str(exc),
        ) from exc
    return {**_APOLLO_BASE_HEADERS, "x-api-key": api_key}


class ApolloCompanyEnrichmentService:

    async def enrich_company(
        self, db: AsyncSession, company: Company, client_id: int
    ) -> Company:
        """Enrich a Company record using the Apollo organization enrichment endpoint.

        1. Set enrichment_status = 'enriching'
        2. Call Apollo GET /v1/organizations/enrich
        3. Map fields onto company
        4. Set enrichment_status = 'enriched', enriched_at = now()
        5. Call auto_link_leads_by_domain
        On any error: set enrichment_status = 'failed', raise EnrichmentProviderError.
        """
        company.enrichment_status = "enriching"
        await db.commit()

        start = time.monotonic()
        logger.info(
            "Apollo org enrichment started",
            extra={"company_id": str(company.id), "client_id": client_id},
        )

        params: dict = {}
        if company.domain:
            params["domain"] = company.domain
        else:
            params["name"] = company.name

        try:
            headers = await _apollo_headers(db)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://api.apollo.io/v1/organizations/enrich",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()

        except httpx.HTTPStatusError as exc:
            company.enrichment_status = "failed"
            await db.commit()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Apollo org enrichment failed: HTTP error",
                extra={
                    "company_id": str(company.id),
                    "client_id": client_id,
                    "status_code": exc.response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            raise EnrichmentProviderError(
                provider="apollo_org",
                lead_id=company.id,  # type: ignore[arg-type]
                reason=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                cause=exc,
            ) from exc

        except httpx.HTTPError as exc:
            company.enrichment_status = "failed"
            await db.commit()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Apollo org enrichment failed: network error",
                extra={
                    "company_id": str(company.id),
                    "client_id": client_id,
                    "error": str(exc),
                    "duration_ms": duration_ms,
                },
            )
            raise EnrichmentProviderError(
                provider="apollo_org",
                lead_id=company.id,  # type: ignore[arg-type]
                reason=str(exc),
                cause=exc,
            ) from exc

        except Exception as exc:
            company.enrichment_status = "failed"
            await db.commit()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Apollo org enrichment failed: unexpected error",
                extra={
                    "company_id": str(company.id),
                    "client_id": client_id,
                    "error": str(exc),
                    "duration_ms": duration_ms,
                },
            )
            raise EnrichmentProviderError(
                provider="apollo_org",
                lead_id=company.id,  # type: ignore[arg-type]
                reason=str(exc),
                cause=exc,
            ) from exc

        # --- Map response fields ---
        org = body.get("organization") or {}

        if not company.name and org.get("name"):
            company.name = org["name"]

        if org.get("website_url"):
            company.website = org["website_url"]

        raw_domain = org.get("primary_domain")
        if raw_domain:
            company.domain = _normalize_domain(raw_domain)

        if org.get("industry"):
            company.industry = org["industry"]
        if org.get("estimated_num_employees") is not None:
            company.employee_count = org["estimated_num_employees"]
        if org.get("city"):
            company.location_city = org["city"]
        if org.get("state"):
            company.location_state = org["state"]
        if org.get("country"):
            company.location_country = org["country"]
        if org.get("id"):
            company.apollo_id = org["id"]
        else:
            logger.warning(
                "Apollo org enrichment: response has no organization.id — "
                "contact pull will not be available for this company",
                extra={"company_id": str(company.id), "client_id": client_id},
            )
        if org.get("funding_stage"):
            company.funding_stage = org["funding_stage"]
        if org.get("annual_revenue_printed"):
            company.annual_revenue_range = org["annual_revenue_printed"]

        techs = org.get("technologies")
        if techs:
            company.tech_stack = [t["name"] for t in techs if isinstance(t, dict) and t.get("name")]

        if org.get("keywords"):
            company.keywords = org["keywords"]
        if org.get("linkedin_url"):
            company.linkedin_url = org["linkedin_url"]
        if org.get("founded_year") is not None:
            company.founded_year = org["founded_year"]

        company.enrichment_data = body
        company.enrichment_status = "enriched"
        company.enriched_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(company)

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "Apollo org enrichment succeeded",
            extra={
                "company_id": str(company.id),
                "client_id": client_id,
                "duration_ms": duration_ms,
            },
        )

        await auto_link_leads_by_domain(db, company, client_id)

        return company

    async def pull_contacts_from_company(
        self,
        db: AsyncSession,
        company: Company,
        client_id: int,
        titles: list[str] | None = None,
        seniorities: list[str] | None = None,
        limit: int = 25,
    ) -> dict:
        """Pull people from Apollo for the given company and upsert them as leads.

        company.apollo_id must be set (enrich the company first).
        Returns summary dict with total_found, pulled, created, updated counts.
        """
        if not company.apollo_id:
            raise ValueError(
                f"Company must be enriched first (apollo_id is missing) — company_id={company.id}"
            )

        start = time.monotonic()
        logger.info(
            "Apollo contact pull started",
            extra={"company_id": str(company.id), "client_id": client_id},
        )

        payload = {
            "organization_ids": [company.apollo_id],
            "person_titles": titles or [],
            "person_seniorities": seniorities or [],
            "per_page": min(limit, 100),
            "page": 1,
        }

        try:
            headers = await _apollo_headers(db)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.apollo.io/v1/mixed_people/api_search",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()

        except httpx.HTTPStatusError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Apollo contact pull failed: HTTP error",
                extra={
                    "company_id": str(company.id),
                    "client_id": client_id,
                    "status_code": exc.response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            raise EnrichmentProviderError(
                provider="apollo_org",
                lead_id=company.id,  # type: ignore[arg-type]
                reason=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                cause=exc,
            ) from exc

        except httpx.HTTPError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Apollo contact pull failed: network error",
                extra={
                    "company_id": str(company.id),
                    "client_id": client_id,
                    "error": str(exc),
                    "duration_ms": duration_ms,
                },
            )
            raise EnrichmentProviderError(
                provider="apollo_org",
                lead_id=company.id,  # type: ignore[arg-type]
                reason=str(exc),
                cause=exc,
            ) from exc

        # api_search may return results under "people" or "contacts" depending on plan/version
        people = body.get("people") or body.get("contacts") or []
        pagination = body.get("pagination") or {}
        total_found = pagination.get("total_entries", len(people))

        logger.info(
            "Apollo contact pull response received",
            extra={
                "company_id": str(company.id),
                "client_id": client_id,
                "response_keys": list(body.keys()),
                "people_count": len(people),
                "total_entries": total_found,
            },
        )

        created_count = 0
        updated_count = 0

        for person in people:
            email = person.get("email")
            if not email:
                logger.warning(
                    "Apollo contact skipped: no email",
                    extra={
                        "apollo_person_id": person.get("id"),
                        "company_id": str(company.id),
                        "client_id": client_id,
                    },
                )
                continue

            first = person.get("first_name") or ""
            last = person.get("last_name") or ""
            name = f"{first} {last}".strip() or email

            person_org = person.get("organization") or {}

            lead_data = LeadCreate(
                name=name,
                email=email,
                title=person.get("title"),
                company=person_org.get("name") or company.name,
                source="apollo_pull",
                apollo_id=person.get("id"),
                enrichment_data=(
                    {"linkedin_url": person["linkedin_url"]}
                    if person.get("linkedin_url")
                    else None
                ),
            )

            lead, action = await upsert_lead(db, lead_data, client_id)

            # Explicitly link to the company we just pulled from
            if lead.company_id is None:
                lead.company_id = company.id
                await db.commit()

            if action == "created":
                created_count += 1
            else:
                updated_count += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "Apollo contact pull completed",
            extra={
                "company_id": str(company.id),
                "client_id": client_id,
                "pulled": len(people),
                "created": created_count,
                "updated": updated_count,
                "duration_ms": duration_ms,
            },
        )

        return {
            "total_found": total_found,
            "pulled": len(people),
            "created": created_count,
            "updated": updated_count,
        }
