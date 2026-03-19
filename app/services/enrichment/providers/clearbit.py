import httpx

from app.core.exceptions import EnrichmentProviderError
from app.services.enrichment.base import EnrichmentProvider, EnrichmentResult

FREEMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "mail.com", "protonmail.com", "zoho.com", "yandex.com",
    "live.com", "msn.com", "gmx.com", "me.com",
})


class ClearbitProvider(EnrichmentProvider):
    provider_name = "clearbit"

    def should_enrich(self, lead) -> bool:
        if not lead.email:
            return False
        domain = lead.email.rsplit("@", 1)[-1].lower()
        if domain in FREEMAIL_DOMAINS:
            return False
        enrichment = lead.enrichment_data or {}
        return "clearbit" not in enrichment

    async def enrich(self, lead, api_key: str) -> EnrichmentResult:
        domain = lead.email.rsplit("@", 1)[-1].lower()

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://company.clearbit.com/v2/companies/find",
                    params={"domain": domain},
                    headers={"Authorization": f"Bearer {api_key}"},
                )

                if resp.status_code == 404:
                    return EnrichmentResult(
                        provider_name=self.provider_name,
                        success=True,
                        data={},
                        raw_response=None,
                        no_data=True,
                    )

                resp.raise_for_status()
                body = resp.json()

            data = {
                "company_name": body.get("name"),
                "industry": body.get("category", {}).get("industry"),
                "sector": body.get("category", {}).get("sector"),
                "employee_count": body.get("metrics", {}).get("employees"),
                "revenue": body.get("metrics", {}).get("estimatedAnnualRevenue"),
                "description": body.get("description"),
            }
            data = {k: v for k, v in data.items() if v is not None}

            return EnrichmentResult(
                provider_name=self.provider_name,
                success=True,
                data=data,
                raw_response=body,
            )
        except httpx.HTTPError as exc:
            raise EnrichmentProviderError(
                provider=self.provider_name,
                lead_id=lead.id,
                reason=str(exc),
                cause=exc,
            ) from exc
